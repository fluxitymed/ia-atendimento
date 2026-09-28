"""Content-free per-turn timing. Watchdogs report, never cancel provider calls."""
from contextvars import ContextVar
from datetime import datetime, timezone
from threading import Timer
import time

active_turn = ContextVar('whatsapp_latency', default=None)


def stamp():
    return {'wall': datetime.now(timezone.utc).isoformat(), 'mono': time.monotonic()}


class TurnLatency:
    limits = {'retrieval': 10, 'model_call': 20, 'outbound': 10, 'turn': 45}

    def __init__(self, logger, identifiers, metadata=None, *, clock=stamp, timer_factory=Timer):
        self.logger = logger
        self.identifiers = identifiers
        self.clock = clock
        self.timer_factory = timer_factory
        self.points = dict((metadata or {}).get('latencyPoints') or {})
        self.points.setdefault('webhook_ingress_received', clock())
        self.points.setdefault('batch_started', self.points['webhook_ingress_received'])
        self.points.setdefault('batch_flushed', self.points['batch_started'])
        self.timers = {}
        self.durations = {}
        self.outbound_sent = False
        self.started = {}
        for name, point in self.points.items():
            self.log(name + '_at', {name + '_at': point['wall']})
        self.watch('turn')

    def log(self, event, details):
        if self.logger:
            self.logger(event, {**self.identifiers, **details})

    def watch(self, stage):
        self.cancel(stage)
        timer = self.timer_factory(self.limits[stage], lambda: self.log('slow_' + stage, {'threshold_ms': self.limits[stage]*1000}))
        timer.daemon = True
        self.timers[stage] = timer
        timer.start()

    def cancel(self, stage):
        timer = self.timers.pop(stage, None)
        if timer: timer.cancel()

    def observe(self, event):
        event = {'model_called': 'model_call_completed', 'outbound_sent': 'outbound_completed'}.get(event, event)
        if event in {'retrieval_failed', 'model_call_failed', 'outbound_failed'}:
            stage = event.removesuffix('_failed')
            self.complete(stage, failed=True)
            return
        if event in {'lock_acquired','runtime_started','retrieval_started','model_call_started','outbound_started'}:
            self.points[event] = self.clock()
            if event.endswith("_started"):
                self.started[event.removesuffix("_started")] = self.points[event]
            self.log(event + '_at', {event + '_at': self.points[event]['wall']})
            stage = event.removesuffix('_started')
            if stage in self.limits: self.watch(stage)
        elif event in {'retrieval_completed', 'model_call_completed', 'outbound_completed'}:
            self.complete(event.removesuffix('_completed'))

    def complete(self, stage, failed=False):
        end = self.clock()
        start = self.started.pop(stage, None)
        # A completion without a start means the stage was skipped.
        if start:
            self.durations[stage] = self.durations.get(stage, 0) + max(0, (end['mono']-start['mono'])*1000)
        self.points[stage+'_completed'] = end
        self.cancel(stage)
        self.log(stage+'_completed_at', {stage+'_completed_at': end['wall'], 'failed': failed})
        if stage == 'outbound' and not failed: self.outbound_sent = True

    def finish(self, outcome):
        for stage in list(self.timers): self.cancel(stage)
        end = self.clock()
        def delta(a, b):
            if a not in self.points or b not in self.points: return None
            return round(max(0, (self.points[b]['mono']-self.points[a]['mono'])*1000), 3)
        self.points['finished'] = end
        metrics = {
            'ingress_to_batch_ms': delta('webhook_ingress_received', 'batch_started'),
            'batch_wait_ms': delta('batch_started', 'batch_flushed'),
            'lock_wait_ms': delta('batch_flushed', 'lock_acquired'),
            'retrieval_ms': round(self.durations.get('retrieval', 0), 3),
            'model_ms': round(self.durations.get('model_call', 0), 3),
            'outbound_ms': round(self.durations.get('outbound', 0), 3),
            'total_processing_ms': delta('lock_acquired', 'finished'),
            'ingress_to_outbound_ms': delta('webhook_ingress_received', 'outbound_completed'),
        }
        self.log('turn_latency_summary', {**metrics, 'outcome': outcome, 'outboundSent': self.outbound_sent})


def observe(event):
    trace = active_turn.get()
    if trace: trace.observe(event)
