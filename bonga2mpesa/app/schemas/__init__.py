from typing import Any, Optional
from pydantic import BaseModel, field_validator, model_validator
from app.core.security import is_valid_kenyan_phone, sanitize_phone


# ── C2B Callback ────────────────────────────────────────────────────────────

class C2BCallbackItem(BaseModel):
    Name: str
    Value: Any


class C2BStkCallbackMetadata(BaseModel):
    Item: list[C2BCallbackItem]

    def get(self, name: str) -> Any:
        for item in self.Item:
            if item.Name == name:
                return item.Value
        return None


class C2BStkCallback(BaseModel):
    MerchantRequestID: str
    CheckoutRequestID: str
    ResultCode: int
    ResultDesc: str
    CallbackMetadata: Optional[C2BStkCallbackMetadata] = None


class C2BPayload(BaseModel):
    Body: dict

    @model_validator(mode="before")
    @classmethod
    def validate_body(cls, v):
        if "Body" not in v:
            raise ValueError("Missing 'Body' in C2B payload")
        return v


class C2BDirectPayload(BaseModel):
    """For Daraja C2B (Paybill) callbacks."""
    TransactionType: str
    TransID: str
    TransTime: str
    TransAmount: str
    BusinessShortCode: str
    BillRefNumber: str
    InvoiceNumber: Optional[str] = None
    OrgAccountBalance: Optional[str] = None
    ThirdPartyTransID: Optional[str] = None
    MSISDN: str
    FirstName: Optional[str] = None
    MiddleName: Optional[str] = None
    LastName: Optional[str] = None

    @field_validator("MSISDN")
    @classmethod
    def validate_msisdn(cls, v):
        if not is_valid_kenyan_phone(v):
            raise ValueError(f"Invalid Kenyan phone number: {v}")
        return sanitize_phone(v)

    @field_validator("TransAmount")
    @classmethod
    def validate_amount(cls, v):
        try:
            amount = float(v)
            if amount <= 0:
                raise ValueError("Amount must be positive")
            return v
        except (TypeError, ValueError):
            raise ValueError(f"Invalid amount: {v}")


# ── B2C Result Callback ──────────────────────────────────────────────────────

class B2CResultParameter(BaseModel):
    Key: str
    Value: Any


class B2CResultParameters(BaseModel):
    ResultParameter: list[B2CResultParameter]

    def get(self, key: str) -> Any:
        for param in self.ResultParameter:
            if param.Key == key:
                return param.Value
        return None


class B2CResult(BaseModel):
    ResultType: int
    ResultCode: int
    ResultDesc: str
    OriginatorConversationID: str
    ConversationID: str
    TransactionID: str
    ResultParameters: Optional[B2CResultParameters] = None


class B2CResultPayload(BaseModel):
    Result: B2CResult


# ── API Responses ────────────────────────────────────────────────────────────

class AcknowledgeResponse(BaseModel):
    ResultCode: str = "00000000"
    ResultDesc: str = "Success"


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None


class TransactionResponse(BaseModel):
    id: str
    phone_number: str
    bonga_points: int
    expected_amount: float
    safaricom_amount: Optional[float]
    payout_amount: Optional[float]
    status: str
    mpesa_receipt: Optional[str]
    correlation_id: str
    created_at: str
