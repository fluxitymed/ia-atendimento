import json
import tempfile
import threading
import unittest
import multiprocessing
import time
from unittest.mock import patch
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, MessageBatchingWhatsAppChannelAdapter, MessageBatchingConfig
from ai_agent_runtime.whatsapp.channel import JsonFileWhatsAppStore


def event(mid='m1', contact='patient', account='account'):
    return dict(providerAccountId=account, providerMessageId=mid, contactExternalId=contact, type='TEXT', text='ola', timestamp='1000')

class Generator:
    def generate(self, state, *, emit):
        return 'Resposta'

class Scheduler:
    def __init__(self): self.tasks=[]; self.now=0
    def now_ms(self): return self.now
    def call_later(self, delay, callback):
        class Handle:
            cancelled=False
            def cancel(self): self.cancelled=True
        h=Handle(); h.callback=callback; h.due=self.now+delay; self.tasks.append(h); return h


def adapter(store=None, generator=None, provider=None, logs=None):
    return WhatsAppChannelAdapter(provider=provider or FakeWhatsAppProvider(), store=store or InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({'account':'org','other':'other-org'}), runtime_graph=AgentRuntimeGraph(response_generator=generator or Generator()), stage_logger=lambda stage, details: logs.append((stage,details)) if logs is not None else None)

def process_worker(path, barrier, output):
    a=adapter(store=JsonFileWhatsAppStore(path))
    barrier.wait(5)
    a.process_event(event())
    output.put(len(a.provider.sent_texts))

class Reliability(unittest.TestCase):
    def test_concurrent_duplicate(self):
        started=threading.Event(); release=threading.Event()
        class Blocking(Generator):
            def generate(self,state,*,emit):
                started.set(); release.wait(2); return 'Resposta'
        a=adapter(generator=Blocking())
        with ThreadPoolExecutor(2) as pool:
            one=pool.submit(a.process_event,event())
            self.assertTrue(started.wait(1))
            two=pool.submit(a.process_event,event())
            release.set(); one.result(); two.result()
        self.assertEqual(a.runtime_calls,1)
        self.assertEqual(len(a.provider.sent_texts),1)

    def test_stale_timer(self):
        a=adapter(); clock=Scheduler(); b=MessageBatchingWhatsAppChannelAdapter(a,scheduler=clock)
        first=b.process_event(event()); stale=clock.tasks[0]
        b.flush(first.inbound.conversation_id)
        second=b.process_event(event('m2'))
        stale.callback() # cancel cannot stop a callback already dispatched
        self.assertEqual(a.runtime_calls,1)
        self.assertIn(second.inbound.conversation_id,b._pending)
        b.flush(second.inbound.conversation_id)
        self.assertEqual(len(a.provider.sent_texts),2)

    def test_corrupt_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'store.json'; path.write_text('{broken')
            with self.assertRaises(Exception): JsonFileWhatsAppStore(path)

    def test_two_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx=multiprocessing.get_context('spawn'); barrier=ctx.Barrier(2); output=ctx.Queue()
            workers=[ctx.Process(target=process_worker,args=(str(Path(tmp)/'store.json'),barrier,output)) for _ in range(2)]
            for worker in workers: worker.start()
            for worker in workers: worker.join(10); self.assertEqual(worker.exitcode,0)
            self.assertEqual(sum(output.get(timeout=2) for _ in workers),1)

    def test_restart_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'store.json'; a=adapter(store=JsonFileWhatsAppStore(path))
            a.process_event(event()); a.process_event(event())
            self.assertEqual(a.runtime_calls,1); self.assertEqual(len(a.provider.sent_texts),1)
            b=adapter(store=JsonFileWhatsAppStore(path)); b.process_event(event())
            self.assertEqual(b.runtime_calls,0); self.assertEqual(len(b.provider.sent_texts),0)
            # A durably accepted but interrupted batch must not resurrect either.
            b.store.reserve_provider_message_key('account:queued')
            c=adapter(store=JsonFileWhatsAppStore(path)); c.process_event(event('queued'))
            self.assertEqual(c.runtime_calls,0)

    def test_ambiguous_outbound(self):
        class TimeoutProvider(FakeWhatsAppProvider):
            def send_text(self, **kwargs):
                super().send_text(**kwargs)
                raise TimeoutError('confirmation lost')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'store.json'; provider=TimeoutProvider(); a=adapter(store=JsonFileWhatsAppStore(path),provider=provider)
            with self.assertRaises(TimeoutError): a.process_event(event())
            a.process_event(event())
            b=adapter(store=JsonFileWhatsAppStore(path),provider=provider); b.process_event(event())
            self.assertEqual(len(provider.sent_texts),1); self.assertEqual(b.runtime_calls,0)
            self.assertEqual(list(b.store.outbound_attempts.values()),['UNKNOWN'])

    def test_before_outbound_failure(self):
        class Broken(Generator):
            def generate(self,state,*,emit): raise RuntimeError('failed')
        a=adapter(generator=Broken())
        with self.assertRaises(Exception): a.process_event(event())
        a.runtime_graph.response_generator=Generator()
        a.process_event(event()); a.process_event(event('m2'))
        self.assertEqual(len(a.provider.sent_texts),1)
        self.assertIn('FAILED_BEFORE_OUTBOUND',a.store.turns.values())

    def test_record_failure_after_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'store.json'; a=adapter(store=JsonFileWhatsAppStore(path))
            with patch.object(a.store,'record',side_effect=OSError('disk failure')):
                with self.assertRaises(OSError): a.process_event(event())
            b=adapter(store=JsonFileWhatsAppStore(path),provider=a.provider); b.process_event(event())
            self.assertEqual(len(a.provider.sent_texts),1)
            self.assertEqual(list(b.store.outbound_attempts.values()),['SENT'])

    def test_write_failure_before_send(self):
        a=adapter()
        with patch.object(a.store,'claim_outbound',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): a.process_event(event())
        self.assertEqual(len(a.provider.sent_texts),0)

    def test_two_messages_batch_and_timer_race(self):
        a=adapter(); clock=Scheduler(); b=MessageBatchingWhatsAppChannelAdapter(a,scheduler=clock)
        first=b.process_event(event()); b.process_event(event('m2'))
        self.assertEqual(sum(not h.cancelled for h in clock.tasks),1)
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(b.flush,first.inbound.conversation_id,reason=reason) for reason in ['DEBOUNCE','MAX_WAIT']]
            for f in futures: f.result()
        self.assertEqual(a.runtime_calls,1); self.assertEqual(len(a.provider.sent_texts),1)
        self.assertEqual(len(a.store.history_for(first.inbound.conversation_id)),1)
        self.assertEqual(a.store.history_for(first.inbound.conversation_id)[0].metadata['batchSize'],2)

    def test_during_flush(self):
        entered=threading.Event(); release=threading.Event()
        class Blocking(Generator):
            def generate(self,state,*,emit): entered.set(); release.wait(2); return 'Resposta'
        a=adapter(generator=Blocking()); clock=Scheduler(); b=MessageBatchingWhatsAppChannelAdapter(a,scheduler=clock)
        first=b.process_event(event()); old=list(clock.tasks)
        with ThreadPoolExecutor(1) as pool:
            running=pool.submit(b.flush,first.inbound.conversation_id)
            self.assertTrue(entered.wait(1))
            b.process_event(event('m2'))
            for handle in old: handle.callback()
            self.assertEqual(len(b._pending[first.inbound.conversation_id].inbound),1)
            release.set(); running.result()
        b.flush(first.inbound.conversation_id)
        self.assertEqual(a.runtime_calls,2); self.assertEqual(len(a.provider.sent_texts),2)

    def test_conversation_isolation(self):
        entered=threading.Event(); release=threading.Event(); other_done=threading.Event(); states=[]
        class Blocking(Generator):
            def generate(self,state,*,emit):
                states.append(state)
                if state.current_message=='block': entered.set(); release.wait(3)
                else: other_done.set()
                emit('isolated_event', {'conversationId':state.conversation_id})
                return 'Resposta'
        a=adapter(generator=Blocking())
        with ThreadPoolExecutor(3) as pool:
            one=pool.submit(a.process_event,{**event(),'text':'block'})
            self.assertTrue(entered.wait(1))
            same=pool.submit(a.process_event,event('m2'))
            other=pool.submit(a.process_event,event('m3','someone-else','other'))
            self.assertTrue(other_done.wait(1)); other.result()
            self.assertFalse(same.done())
            release.set(); one.result(); same.result()
        self.assertEqual(len(a.provider.sent_texts),3)
        for state in states:
            markers=[e for e in state.context['runtimeEvents'] if e['stage']=='isolated_event']
            self.assertEqual(len(markers),1)
            self.assertEqual(markers[0]['details']['conversationId'],state.conversation_id)

    def test_callbacks_aliases(self):
        from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post
        from ai_agent_runtime.whatsapp.zapi import ZApiWhatsAppConfig
        a=adapter(); config=ZApiWhatsAppConfig(instance_id='account')
        def post(payload): return handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(),headers={},config=config,adapter=a)
        raw=dict(instanceId='account', messageId='self',phone='557100000000',type='ReceivedCallback',fromMe=True,text={'message':'ola'})
        post(raw); post({**raw,'type':'DeliveryCallback','fromMe':False,'messageId':'status'})
        self.assertEqual(a.runtime_calls,0); self.assertEqual(len(a.provider.sent_texts),0)
        post({**raw,'fromMe':False,'messageId':'one','senderLid':'abc@lid'})
        post({**raw,'phone':'abc@lid','fromMe':False,'messageId':'two'})
        self.assertEqual(len(a.provider.sent_texts),2)
        self.assertEqual(len(a.store.messages_by_conversation),1)
        a.process_event(event('one',contact='557100000000',account='other'))
        self.assertEqual(len(a.provider.sent_texts),3)
        self.assertEqual(len(a.store.messages_by_conversation),2)

    def test_fast_ingress(self):
        from ai_agent_runtime.whatsapp.ingress import AsyncWhatsAppIngress, IngressBusy
        entered=threading.Event(); release=threading.Event()
        class Blocking(Generator):
            def generate(self,state,*,emit): entered.set(); release.wait(2); return 'Resposta'
        a=adapter(generator=Blocking()); ingress=AsyncWhatsAppIngress(a,workers=1,capacity=1)
        try:
            start=time.monotonic(); ingress.process_event(event())
            self.assertLess(time.monotonic()-start,0.3)
            self.assertTrue(entered.wait(1)); ingress.process_event(event())
            with self.assertRaises(IngressBusy): ingress.process_event(event('m2'))
            self.assertFalse(a.store.has_seen_provider_message_key('account:m2'))
        finally: release.set(); ingress.close()
        self.assertEqual(len(a.provider.sent_texts),1)

    def test_latency(self):
        from ai_agent_runtime.whatsapp.latency import TurnLatency
        now=[0]; logs=[]; timers=[]
        def clock(): return {'wall':str(now[0]),'mono':now[0]}
        class Timer:
            def __init__(self,delay,callback): self.callback=callback; self.cancelled=False; timers.append(self)
            def start(self): pass
            def cancel(self): self.cancelled=True
        trace=TurnLatency(lambda e,d:logs.append((e,d)),dict(organizationId='o',conversationId='c',runtimeInvocationId='r',providerMessageId='p'),{'latencyPoints':{'webhook_ingress_received':clock()}},clock=clock,timer_factory=Timer)
        now[0]=6; trace.points['batch_flushed']=clock(); trace.observe('lock_acquired'); trace.observe('runtime_started')
        for stage,duration in [('retrieval',2),('model_call',3),('outbound',1)]:
            trace.observe(stage+'_started'); timers[-1].callback(); now[0]+=duration; trace.observe(stage+'_completed')
        timers[0].callback(); trace.finish('PROCESSED')
        result=logs[-1][1]
        self.assertEqual(result['batch_wait_ms'],6000); self.assertEqual(result['retrieval_ms'],2000)
        self.assertEqual(result['model_ms'],3000); self.assertEqual(result['outbound_ms'],1000)
        self.assertEqual(result['ingress_to_outbound_ms'],12000); self.assertTrue(result['outboundSent'])
        self.assertEqual(result['total_processing_ms'],6000); self.assertEqual(result['lock_wait_ms'],0)
        self.assertEqual(set(result),{'organizationId','conversationId','runtimeInvocationId','providerMessageId','ingress_to_batch_ms','batch_wait_ms','lock_wait_ms','retrieval_ms','model_ms','outbound_ms','total_processing_ms','ingress_to_outbound_ms','outcome','outboundSent'})
        for stage in ['retrieval','model_call','outbound','turn']: self.assertTrue(any(e=='slow_'+stage for e,d in logs))
        self.assertTrue(all(t.cancelled for t in timers))
        actual=[]; a=adapter(logs=actual); a.process_event({**event(),'text':'private patient content'})
        summary=[d for e,d in actual if e=='turn_latency_summary']
        self.assertEqual(len(summary),1); self.assertTrue(summary[0]['outboundSent'])
        self.assertNotIn('private',json.dumps(summary))

    def test_http_media_and_early(self):
        from ai_agent_runtime.whatsapp.ingress import AsyncWhatsAppIngress
        from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post
        from ai_agent_runtime.whatsapp.zapi import ZApiWhatsAppConfig
        from ai_agent_runtime.whatsapp.media import MediaProcessingResult, MediaDecision
        for kind in ('audio','early'):
            entered=threading.Event(); release=threading.Event()
            class Blocking(Generator):
                def generate(self,state,*,emit): entered.set(); release.wait(2); return 'Resposta'
            class Media:
                def process(self,**kwargs):
                    entered.set(); release.wait(2)
                    return MediaProcessingResult(decision=MediaDecision.MEDIA_RETRY_REQUIRED)
            a=adapter(generator=Blocking()); a.media_processor=Media()
            ingress=AsyncWhatsAppIngress(MessageBatchingWhatsAppChannelAdapter(a))
            payload=dict(instanceId='account',messageId=kind,phone='557100000000',fromMe=False,type='ReceivedCallback')
            payload.update({'audio':{'audioUrl':'https://example.invalid/audio'}} if kind=='audio' else {'text':{'message':'muita dor'}})
            try:
                before=time.monotonic()
                response,_=handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(),headers={},config=ZApiWhatsAppConfig(),adapter=ingress)
                self.assertEqual(response.status_code,200); self.assertLess(time.monotonic()-before,.3)
                self.assertTrue(entered.wait(1))
            finally: release.set(); ingress.close()
            self.assertEqual(len(a.provider.sent_texts),1)

    def test_service_singleton(self):
        from ai_agent_runtime.whatsapp.zapi_server import _acquire_service_lock
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',{'ZAPI_STORE_PATH':str(Path(tmp)/'store.json')}):
            first=_acquire_service_lock()
            try:
                with self.assertRaisesRegex(RuntimeError,'ALREADY_RUNNING'): _acquire_service_lock()
            finally: first.close()
            second=_acquire_service_lock(); second.close()

    def test_disk_failure_and_disappearance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'store.json'; store=JsonFileWhatsAppStore(path)
            store.reserve_provider_message_key('account:one')
            with patch('ai_agent_runtime.whatsapp.channel.os.fsync', side_effect=OSError('disk error')):
                with self.assertRaises(OSError): store.reserve_provider_message_key('account:two')
            reloaded=JsonFileWhatsAppStore(path)
            self.assertTrue(reloaded.has_seen_provider_message_key('account:one'))
            self.assertFalse(reloaded.has_seen_provider_message_key('account:two'))
            path.unlink()
            with self.assertRaisesRegex(RuntimeError,'DISAPPEARED'): store.has_seen_provider_message_key('account:one')

    def test_batch_concurrent_duplicate(self):
        a=adapter(); b=MessageBatchingWhatsAppChannelAdapter(a,scheduler=Scheduler()); barrier=threading.Barrier(2)
        def run(): barrier.wait(2); return b.process_event(event())
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(run) for _ in range(2)]
            records=[f.result() for f in futures]
        for key in list(b._pending): b.flush(key)
        self.assertEqual(a.runtime_calls,1); self.assertEqual(len(a.provider.sent_texts),1)
        self.assertEqual(sum(r.decision.value=='DUPLICATE_SUPPRESSED' for r in records),1)

if __name__=='__main__': unittest.main()
