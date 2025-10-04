from pydantic import BaseModel


class AnonymizationMeta(BaseModel):
    correlation_id: str
    elapsed_s: float


class AnonymizationRequest(BaseModel):
    data: str


class AnonymizationResponse(BaseModel):
    anonymized: str
    meta: AnonymizationMeta
