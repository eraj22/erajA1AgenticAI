"""Environment-only configuration. Never serialize settings into a response."""
import json
from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    host: str = '127.0.0.1'
    port: int = Field(default=8000, ge=1, le=65535)
    model_provider: Literal['gemini', 'anthropic', 'unconfigured'] = 'unconfigured'
    model_name: str = 'demo'
    model_names: str = ''
    enable_demo: bool = True
    gemini_api_key: SecretStr = SecretStr('')
    anthropic_api_key: SecretStr = SecretStr('')
    model_prices_json: str = '{}'
    max_steps: int = Field(default=6, ge=1, le=6)
    max_tool_retries: int = Field(default=2, ge=0, le=2)
    max_contract_retries: int = Field(default=2, ge=0, le=2)
    max_output_tokens: int = Field(default=1024, ge=128, le=4096)
    max_run_tokens: int = Field(default=60000, ge=1024, le=200000)
    max_run_cost_usd: float = Field(default=0.05, gt=0, le=10)
    run_timeout_seconds: float = Field(default=40, gt=0, le=40)
    model_timeout_seconds: float = Field(default=15, gt=0, le=40)
    tool_timeout_seconds: float = Field(default=2, gt=0, le=10)
    history_messages: int = Field(default=12, ge=2, le=12)
    history_chars: int = Field(default=24000, ge=100, le=24000)
    max_context_bytes: int = Field(default=32000, ge=1000, le=64000)
    max_sessions: int = Field(default=100, ge=1, le=1000)
    max_concurrent_runs: int = Field(default=2, ge=1, le=10)
    requests_per_minute: int = Field(default=30, ge=1, le=300)
    max_daily_model_calls: int = Field(default=200, ge=1, le=5000)

    @model_validator(mode='after')
    def validate_prices(self):
        prices = json.loads(self.model_prices_json)
        if not isinstance(prices, dict):
            raise ValueError('MODEL_PRICES_JSON must be an object')
        for price in prices.values():
            if set(price) != {'input', 'output'} or any(type(v) not in (int, float) or v < 0 for v in price.values()):
                raise ValueError('Prices require nonnegative input/output USD per million tokens')
        return self

    def enabled_models(self):
        key = self.gemini_api_key if self.model_provider == 'gemini' else self.anthropic_api_key
        live = []
        if self.model_provider != 'unconfigured' and key.get_secret_value():
            live = [m.strip() for m in self.model_names.split(',') if m.strip()]
            if self.model_name and self.model_name != 'demo':
                live.insert(0, self.model_name)
        return list(dict.fromkeys(live + (['demo'] if self.enable_demo else [])))

settings = Settings()

