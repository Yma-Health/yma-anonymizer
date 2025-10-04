import time
import uuid
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, HTTPException, status

from app.container import container
from app.models import AnonymizationMeta, AnonymizationRequest, AnonymizationResponse
from app.services import LLMService, SimplexService
from app.services.simplex import SimplexPatientVisitHistoryResponse

logger = structlog.get_logger("app.main")

app = FastAPI(title="Yma Anonymization Middleware")


def get_llm_service() -> LLMService:
    return container[LLMService]


def get_simplex_service() -> SimplexService:
    return container[SimplexService]


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/anonymize", response_model=AnonymizationResponse)
async def anonymize(
    request: AnonymizationRequest,
    *,
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> AnonymizationResponse:
    corr_id = str(uuid.uuid4())
    log = logger.bind(correlation_id=corr_id)
    start_time = time.monotonic()

    try:
        anonymized = await llm.anonymize(request.data)
    except Exception as e:
        log.error("Anonymization failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e

    if anonymized is None:
        log.error("No anonymized data returned")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No anonymized data returned")

    log.info("Anonymized data")

    elapsed_s = round(time.monotonic() - start_time, 2)
    log.info("Anonymization completed", elapsed_s=elapsed_s)
    return AnonymizationResponse(
        anonymized=anonymized,
        meta=AnonymizationMeta(
            correlation_id=corr_id,
            elapsed_s=elapsed_s,
        ),
    )


@app.get("/ehr/patient-visit-histories", response_model=SimplexPatientVisitHistoryResponse)
async def patient_visit_histories(
    permanent_mrn_no: str,
    permanent_visit_no: str,
    *,
    simplex: Annotated[SimplexService, Depends(get_simplex_service)],
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> SimplexPatientVisitHistoryResponse:
    try:
        resp = await simplex.get_patient_visit_history(
            permanent_mrn_no=permanent_mrn_no,
            permanent_visit_no=permanent_visit_no,
        )
    except Exception as e:
        logger.error("Simplex patient visit history fetch failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch patient visit history",
        ) from e

    try:
        anonymized_message = await llm.anonymize(resp.message)
    except Exception as e:
        logger.error("Message anonymization failed", error=str(e), exc_info=True)
        anonymized_message = None

    if anonymized_message is None:
        anonymized_message = resp.message

    return resp.model_copy(update={"message": anonymized_message})
