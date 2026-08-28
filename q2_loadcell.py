"""QIDI Q2 probe_air to upstream Klipper load-cell compatibility layer.

This module samples the CS1237 through QIDI's synchronous
probe_air.sensor_helper.read_origin_data() query.  It does not reconfigure the
ADC or register a second MCU sensor, so the stock probe_air implementation
remains in control of probing.
"""

import logging
import statistics


class Q2Sensor(object):
    def __init__(self, owner, samples_per_second):
        self._owner = owner
        self._sps = float(samples_per_second)

    def get_samples_per_second(self):
        return self._sps

    def get_mcu(self):
        return self._owner.mcu

    def get_range(self):
        return (-8388608, 8388607)

    def get_status(self, eventtime):
        return {
            'errors': self._owner.read_errors,
            'overflows': 0,
            'sample_rate': self._sps,
        }


class Q2SampleCollector(object):
    def __init__(self, owner):
        self._owner = owner
        self._printer = owner.printer
        self._reactor = owner.reactor
        self._mcu = owner.mcu
        self.min_time = 0.0
        self.max_time = float('inf')
        self.min_count = float('inf')
        self.is_started = False
        self._samples = []
        self._tare_counts = None
        self._start_errors = 0

    def _on_sample(self, print_time, counts):
        # AutoPA's abort guard sets is_started directly.  Returning False here
        # makes the shared poller unsubscribe this collector on its next tick.
        if not self.is_started:
            return False
        if self.min_time <= print_time <= self.max_time:
            tare = self._tare_counts
            force = -(counts - tare)
            self._samples.append([print_time, force, counts, tare])
        if print_time > self.max_time or len(self._samples) >= self.min_count:
            self.is_started = False
        return self.is_started

    def start_collecting(self, min_time=None):
        if self.is_started:
            return
        self.min_time = min_time if min_time is not None else 0.0
        self.max_time = float('inf')
        self.min_count = float('inf')
        self._samples = []
        self._start_errors = self._owner.read_errors
        # AutoPA has no explicit tare call.  Take a fresh, median tare before
        # every acquisition while the machine is stationary.
        self._tare_counts = self._owner.measure_tare()
        self.is_started = True
        self._owner.add_client(self._on_sample)

    def _finish_collecting(self):
        self.is_started = False
        self._owner.remove_client(self._on_sample)
        samples = self._samples
        self._samples = []
        errors = max(0, self._owner.read_errors - self._start_errors)
        return samples, ((errors, 0) if errors else 0)

    def stop_collecting(self):
        return self._finish_collecting()

    def _collect_until(self, timeout):
        while self.is_started:
            now = self._reactor.monotonic()
            if self._mcu.estimated_print_time(now) > timeout:
                samples, errors = self._finish_collecting()
                raise self._printer.command_error(
                    "Q2 load-cell collector timed out: %d samples, errors=%s"
                    % (len(samples), errors))
            self._reactor.pause(now + 0.025)
        return self._finish_collecting()

    def collect_min(self, min_count=1):
        self.min_count = min_count
        if len(self._samples) >= min_count:
            return self._finish_collecting()
        now_pt = self._mcu.estimated_print_time(self._reactor.monotonic())
        start_pt = max(now_pt, self.min_time)
        timeout = start_pt + 1.5 + min_count / self._owner.sensor.get_samples_per_second()
        return self._collect_until(timeout)

    def collect_until(self, print_time=None):
        if print_time is None:
            print_time = self._mcu.estimated_print_time(
                self._reactor.monotonic())
        self.max_time = float(print_time)
        if self._samples and self._samples[-1][0] >= self.max_time:
            return self._finish_collecting()
        return self._collect_until(self.max_time + 1.5)


class Q2LoadCell(object):
    cmd_QPA_SENSOR_TEST_help = (
        "Safely sample the QIDI Q2 nozzle load cell without movement or extrusion")

    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.name = 'q2_loadcell'
        self.config_name = config.get_name()
        # read_origin_data() is a synchronous MCU query, not a cached-property
        # access.  40Hz keeps queries safely below the QIDI command path's
        # saturation point while still meeting AutoPA's timing needs.
        self.poll_hz = config.getfloat('poll_hz', 40.0, minval=20.0,
                                       maxval=80.0)
        self.tare_time = config.getfloat('tare_time', 0.35, minval=0.15,
                                         maxval=2.0)
        self.configured_sps = config.getfloat('samples_per_second', 40.0,
                                               minval=20.0, maxval=100.0)
        self.sensor = Q2Sensor(self, self.configured_sps)
        self.read_errors = 0
        self.poll_calls = 0
        self.new_readings = 0
        self.duplicate_reads = 0
        self.tare_counts = None
        self.reference_tare_counts = None
        self.counts_per_gram = None
        self._clients = []
        self._last_raw = None
        self._poll_timer = self.reactor.register_timer(
            self._poll, self.reactor.NEVER)
        self._reader = None
        self.mcu = None
        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.gcode.register_command('QPA_SENSOR_TEST', self.cmd_QPA_SENSOR_TEST,
                                    desc=self.cmd_QPA_SENSOR_TEST_help)
        # AutoPA resolves the conventional object name.  Do not replace a real
        # upstream [load_cell] should one ever be configured.
        if self.printer.lookup_object('load_cell', None) is None:
            self.printer.add_object('load_cell', self)

    def _handle_ready(self):
        probe = self.printer.lookup_object('probe_air')
        helper = probe.sensor_helper
        self._reader = helper.read_origin_data
        self.mcu = helper.get_mcu()

    def _ensure_ready(self):
        if self._reader is None or self.mcu is None:
            self._handle_ready()

    def _read_raw(self):
        self.poll_calls += 1
        try:
            value = self._reader()
            if value is None:
                self.read_errors += 1
                return None
            return int(value)
        except Exception:
            self.read_errors += 1
            logging.exception("q2_loadcell: read_origin_data failed")
            return None

    def _poll(self, eventtime):
        if not self._clients:
            return self.reactor.NEVER
        raw = self._read_raw()
        if raw is not None:
            # CS1237 config 0x3c selects 1280Hz conversion.  Calls are spaced
            # at 25ms, so every successful query is newer than the previous
            # conversion even when quantisation happens to repeat the same code.
            if raw == self._last_raw:
                self.duplicate_reads += 1
            self._last_raw = raw
            self.new_readings += 1
            print_time = self.mcu.estimated_print_time(eventtime)
            keep = []
            for callback in list(self._clients):
                try:
                    if callback(print_time, raw):
                        keep.append(callback)
                except Exception:
                    self.read_errors += 1
                    logging.exception("q2_loadcell: sample client failed")
            self._clients = keep
        if not self._clients:
            return self.reactor.NEVER
        return eventtime + 1.0 / self.poll_hz

    def add_client(self, callback):
        if callback not in self._clients:
            self._clients.append(callback)
        self._ensure_ready()
        self.reactor.update_timer(self._poll_timer, self.reactor.NOW)

    def remove_client(self, callback):
        self._clients = [cb for cb in self._clients if cb != callback]

    def measure_tare(self):
        self._ensure_ready()
        values = []
        deadline = self.reactor.monotonic() + self.tare_time

        def capture_tare(print_time, counts):
            values.append(counts)
            return self.reactor.monotonic() < deadline

        self.add_client(capture_tare)
        try:
            while self.reactor.monotonic() < deadline:
                now = self.reactor.monotonic()
                self.reactor.pause(min(deadline, now + 0.025))
        finally:
            self.remove_client(capture_tare)
        if len(values) < 4:
            raise self.printer.command_error(
                "Q2 load-cell tare failed: only %d new ADC readings" % len(values))
        self.tare_counts = int(round(statistics.median(values)))
        self.reference_tare_counts = self.tare_counts
        self.printer.send_event('load_cell:tare', self)
        return self.tare_counts

    def get_collector(self):
        return Q2SampleCollector(self)

    def get_sensor(self):
        return self.sensor

    def tare(self, tare_counts):
        self.tare_counts = int(round(tare_counts))
        self.reference_tare_counts = self.tare_counts
        self.printer.send_event('load_cell:tare', self)

    def get_status(self, eventtime):
        return {
            'is_calibrated': False,
            'counts_per_gram': None,
            'reference_tare_counts': self.reference_tare_counts,
            'tare_counts': self.tare_counts,
            'errors': self.read_errors,
            'overflows': 0,
            'sample_rate': self.configured_sps,
            'poll_calls': self.poll_calls,
            'new_readings': self.new_readings,
            'duplicate_reads': self.duplicate_reads,
        }

    def cmd_QPA_SENSOR_TEST(self, gcmd):
        duration = gcmd.get_float('TIME', 5.0, minval=1.0, maxval=30.0)
        collector = self.get_collector()
        poll0 = self.poll_calls
        dup0 = self.duplicate_reads
        err0 = self.read_errors
        start_wall = self.reactor.monotonic()
        try:
            collector.start_collecting()
            measurement_start = self.reactor.monotonic()
            deadline = measurement_start + duration
            while self.reactor.monotonic() < deadline:
                now = self.reactor.monotonic()
                self.reactor.pause(min(deadline, now + 0.025))
            samples, errors = collector.stop_collecting()
        finally:
            if collector.is_started:
                collector.stop_collecting()
        elapsed = self.reactor.monotonic() - measurement_start
        if not samples:
            raise gcmd.error("QPA sensor test returned no new ADC readings")
        counts = [row[2] for row in samples]
        sigma = statistics.pstdev(counts) if len(counts) > 1 else 0.0
        span = max(counts) - min(counts)
        if len(samples) > 1 and samples[-1][0] > samples[0][0]:
            effective_rate = (len(samples) - 1) / (samples[-1][0] - samples[0][0])
        else:
            effective_rate = 0.0
        gcmd.respond_info(
            "Q2 LOAD CELL TEST OK\n"
            "samples/adc_reads: %d\n"
            "elapsed: %.3f s\n"
            "effective_rate: %.2f Hz\n"
            "configured_sps: %.2f Hz\n"
            "tare_median: %d\n"
            "sigma: %.1f\n"
            "span: %d\n"
            "unique_values: %d\n"
            "poll_calls: %d\n"
            "same_value_polls: %d\n"
            "read_errors: %d\n"
            "collector_errors: %s"
            % (len(samples), elapsed, effective_rate, self.configured_sps,
               collector._tare_counts, sigma, span, len(set(counts)),
               self.poll_calls - poll0, self.duplicate_reads - dup0,
               self.read_errors - err0, errors))


def load_config(config):
    return Q2LoadCell(config)
