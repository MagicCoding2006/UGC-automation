from typing import Literal
from pydantic import BaseModel, Field, field_validator


class Product(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    category: str = Field(default='General', max_length=100)
    description: str = Field(min_length=10, max_length=3000)
    audience: str = Field(min_length=3, max_length=500)
    claims: list[str] = Field(min_length=1, max_length=20)
    forbidden_claims: list[str] = Field(default_factory=list, max_length=30)
    hooks: list[str] = Field(default_factory=lambda: ['Take a closer look.', 'A simpler everyday essential.'], min_length=1, max_length=30)
    cta: str = Field(default='See the details.', max_length=150)
    landing_url: str = Field(default='', max_length=2000)
    price: float = Field(gt=0, le=1000000)
    lifetime_orders: float = Field(default=1, ge=1, le=100)
    contribution_margin: float = Field(default=.5, gt=0, le=1)
    color: str = '#b8f36b'
    is_example: bool = False

    @field_validator('color')
    @classmethod
    def color_hex(cls, v):
        import re
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', v):
            raise ValueError('Use a six-digit hex color')
        return v

    @field_validator('claims', 'forbidden_claims', 'hooks')
    @classmethod
    def clean_lines(cls, values):
        if any(not s.strip() or len(s) > 250 for s in values):
            raise ValueError('Each line must contain 1–250 characters')
        return [s.strip() for s in values]

    @field_validator('landing_url')
    @classmethod
    def http_url(cls, v):
        if v and not v.startswith(('https://', 'http://')):
            raise ValueError('Use an HTTP or HTTPS landing page')
        return v


class Creator(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=20, max_length=2000)
    voice: Literal['af_heart', 'af_bella', 'af_nicole', 'af_sarah', 'af_sky', 'am_adam', 'am_michael', 'am_liam'] = 'af_heart'
    reference_asset_id: str | None = None
    rights: str = Field(default='Original fictional synthetic persona', min_length=10, max_length=1000)
    color: str = '#ddb6fe'
    generated: bool = True


ModelID = Literal['demo', 'remix', 'fabric-480', 'fabric-720', 'infinitetalk', 'wan-local']


class Batch(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    product_id: str
    creator_ids: list[str] = Field(min_length=1, max_length=30)
    models: list[ModelID] = Field(default=['demo'], min_length=1, max_length=6)
    count: int = Field(default=3, ge=1, le=1000)
    budget: float = Field(default=10, ge=0, le=100000)
    duration: Literal[15, 20, 30] = 15
    experiment: Literal['hook', 'creator', 'model', 'mixed'] = 'hook'
    seed: int = Field(default=42, ge=0, le=2147483647)
    hook_index: int = Field(default=0, ge=0)
    caption_style: Literal['bold', 'minimal'] = 'bold'
    # Human-provided footage can be reused; it must be approved and rights-recorded.
    asset_ids: list[str] = Field(default_factory=list, max_length=30)


class Review(BaseModel):
    decision: Literal['approved', 'rejected']
    realism: int = Field(ge=1, le=5)
    lipsync: int = Field(ge=1, le=5)
    product_accuracy: int = Field(ge=1, le=5)
    notes: str = Field(default='', max_length=3000)


class Automation(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    batch: Batch
    interval_hours: float = Field(default=24, ge=1, le=8760)
    enabled: bool = True


class Metric(BaseModel):
    job_id: str
    platform: Literal['tiktok', 'facebook', 'instagram', 'other']
    date: str
    impressions: int = Field(ge=0)
    views: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    customers: int = Field(default=0, ge=0)
    revenue: float = Field(default=0, ge=0)
    media_spend: float = Field(default=0, ge=0)

    @field_validator('date')
    @classmethod
    def iso_date(cls, v):
        from datetime import date
        date.fromisoformat(v)
        return v
