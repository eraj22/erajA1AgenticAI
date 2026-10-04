import json
import unittest
from unittest.mock import patch
import httpx
from pydantic import SecretStr
from app.config import settings
from app.models import AgentState
from app.providers import LiveModel, ProviderError, daily_calls, DailyBudgetReached

class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_request_and_usage(self):
        def handler(request):
            self.assertEqual(request.headers['x-goog-api-key'],'test-key')
            body=json.loads(request.content)
            self.assertIn('responseJsonSchema',body['generationConfig'])
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'{"status":"blocked"}'}]}}],
                'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':10,'thoughtsTokenCount':3}})
        with patch.object(settings,'model_provider','gemini'),patch.object(settings,'gemini_api_key',SecretStr('test-key')):
            r=await LiveModel('test-model',httpx.MockTransport(handler)).decide([{'content':'policy'},{'content':'goal'}],AgentState(goal='x'))
        self.assertEqual((r.input_tokens,r.output_tokens),(100,13))

    async def test_anthropic_request_and_usage(self):
        def handler(request):
            self.assertEqual(request.headers['x-api-key'],'test-key')
            self.assertEqual(json.loads(request.content)['system'],'policy')
            return httpx.Response(200,json={'content':[{'type':'text','text':'{"status":"blocked"}'}],'usage':{'input_tokens':80,'output_tokens':9}})
        with patch.object(settings,'model_provider','anthropic'),patch.object(settings,'anthropic_api_key',SecretStr('test-key')):
            r=await LiveModel('test-model',httpx.MockTransport(handler)).decide([{'content':'policy'},{'role':'user','content':'goal'}],AgentState(goal='x'))
        self.assertEqual(r.input_tokens,80)

    async def test_http_error_is_sanitized(self):
        with patch.object(settings,'model_provider','gemini'),patch.object(settings,'gemini_api_key',SecretStr('private-key')):
            with self.assertRaises(ProviderError) as caught:
                await LiveModel('test-model',httpx.MockTransport(lambda r:httpx.Response(503,text='sensitive upstream text'))).decide([{'content':'p'},{'content':'g'}],AgentState(goal='x'))
        self.assertEqual(caught.exception.code,'provider_http_error')
        self.assertTrue(caught.exception.retryable)
        self.assertNotIn('private-key',str(caught.exception))

    async def test_invalid_model_cannot_change_provider_url(self):
        with self.assertRaises(ProviderError): LiveModel('../../somewhere')

    async def test_daily_call_cap(self):
        with patch.object(settings,'max_daily_model_calls',1):
            daily_calls.day=-1
            daily_calls.reserve()
            with self.assertRaises(DailyBudgetReached): daily_calls.reserve()
        daily_calls.day=-1

if __name__=='__main__':
    unittest.main()
