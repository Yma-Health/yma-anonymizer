from __future__ import annotations

import datetime as dt
from time import monotonic
from typing import Any

import httpx
from pydantic import BaseModel, Field
from structlog import get_logger, BoundLogger
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import SimplexConfig

logger = get_logger(__name__)


# === Pydantic models matching Simplex payload ===


class SimplexAppointmentInfo(BaseModel):
    doctor_name: str
    doctor_id: str
    doctor_speciality: str
    appointment_type: str
    appointment_start_date_time: str
    appointmet_end_date_time: str
    appointment_create_date_time: str
    appointment_modification_date_time: str
    appointment_id: str
    appointment_status: str
    CPT_code_service: str
    ID_service: str
    Description_service: str
    appointment_note: str | None = None
    Appointment_taken_from: str | None = None


class SimplexAppointmentRecord(BaseModel):
    patient_id: str
    Permanent_MRNo: str
    Temporary_MRN_No: str
    patient_first_name: str
    patient_last_name: str | None = None
    mobile_number: str
    mobile_country_code: str | None = None
    email_id: str | None = None
    Source_of_Contact: str | None = None
    appointment: SimplexAppointmentInfo


class SimplexAppointmentsResponse(BaseModel):
    error_count: int
    message: str
    result_count: int
    data: list[SimplexAppointmentRecord] = Field(default_factory=list)


# === Patient Visit History (v2) ===


class SimplexPatientVisitHistoryItem(BaseModel):
    Patient_Visit_Medical_Family_Social_History_Details_Serial_No: str
    Patient_Basic_Details_Serial_No: str
    Patient_Visit_Basic_Details_Serial_No: str
    Past_MH: str
    Is_Past_MH_a_Warning: str
    Past_Surgical_MH: str
    Is_Past_Surgical_MH_a_Warning: str
    Other_Family_MH: str
    Is_Other_Family_MH_a_Warning: str
    Med_Fam_Social_History_Note: str
    Is_Med_Fam_Social_History_Note_a_Warning: str
    Permanent_MRN_No: str
    Permanent_Visit_No: str
    Patient_Visit_Registration_Note: str | None = None
    Patient_Visit_Registered_Date_Time: str
    Active_Status: str


class SimplexPatientVisitHistoryResponse(BaseModel):
    status: bool
    message: str
    data: list[SimplexPatientVisitHistoryItem] = Field(default_factory=list)


# === Exceptions ===


class SimplexError(Exception):
    pass


class SimplexNetworkError(SimplexError):
    pass


class SimplexAuthError(SimplexError):
    pass


class SimplexNotFoundError(SimplexError):
    pass


class SimplexRateLimitError(SimplexError):
    pass


class SimplexClientError(SimplexError):
    pass


class SimplexServerError(SimplexError):
    pass


# === Retry policy ===


SIMPLEX_RETRY_ATTEMPTS = 3


def _log_retry_request(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "Retrying Simplex request",
        attempt=retry_state.attempt_number,
        wait_seconds=(retry_state.next_action.sleep if retry_state.next_action is not None else None),
        last_error=(str(exc) if exc else None),
        error_type=(type(exc).__name__ if exc else None),
    )


simplex_retry = retry(
    reraise=True,
    stop=stop_after_attempt(SIMPLEX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=2, max=120, exp_base=2),
    retry=retry_if_exception_type((SimplexNetworkError, SimplexServerError, SimplexRateLimitError)),
    before_sleep=_log_retry_request,
)


# === Service ===


class SimplexService:
    def __init__(self, config: SimplexConfig):
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=self._build_api_base_url(),
            timeout=self.config.timeout_seconds,
            headers=self._default_headers(),
        )

    def _build_api_base_url(self) -> str:
        # For v1 endpoints we call /api, for v2 we will pass absolute path starting with /v2
        return f"{self.config.base_url.rstrip('/')}/{self.config.tenant_path.strip('/')}/api"

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "yma-anonymizer/1.0 (+https://reforma.health)",
        }
        return headers

    def _log_error_response(self, response: httpx.Response, log: BoundLogger) -> None:
        try:
            body = response.json()
            log.error("simplex_error_response", status_code=response.status_code, body=body)
        except Exception:
            log.error("simplex_error_response", status_code=response.status_code, body=response.text)

    @simplex_retry
    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start_ts = monotonic()
        log = logger.bind(http_method=method, url=url)

        try:
            response = await self._client.request(
                method,
                url,
                params=params,
                json=json,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            log.warning("network_error", error=str(exc))
            raise SimplexNetworkError("Network error during Simplex request") from exc

        if httpx.codes.OK <= response.status_code < httpx.codes.MULTIPLE_CHOICES:
            log.info("success", duration_ms=int((monotonic() - start_ts) * 1000))
            try:
                return response.json()
            except Exception as exc:
                log.error("invalid_json", error=str(exc))
                raise SimplexClientError("Failed to parse JSON response") from exc

        if response.status_code == httpx.codes.UNAUTHORIZED:
            self._log_error_response(response, log)
            raise SimplexAuthError("Unauthorized: invalid Simplex API token")
        if response.status_code == httpx.codes.NOT_FOUND:
            self._log_error_response(response, log)
            raise SimplexNotFoundError("Resource not found in Simplex")
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            self._log_error_response(response, log)
            raise SimplexRateLimitError("Rate limit exceeded")

        if httpx.codes.BAD_REQUEST <= response.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
            self._log_error_response(response, log)
            raise SimplexClientError(f"Client error from Simplex: {response.status_code}")

        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            self._log_error_response(response, log)
            raise SimplexServerError(f"Server error from Simplex: {response.status_code}")

        self._log_error_response(response, log)
        raise SimplexClientError(f"Unexpected status from Simplex: {response.status_code}")

    async def appointments_by_date(self, *, date: dt.date) -> SimplexAppointmentsResponse:
        params = {
            "location_id": self.config.location_id,
            "api_key": self.config.api_key,
            "date": date.isoformat(),
        }
        log = logger.bind(endpoint="appointments-by-date", date=params["date"])
        log.info("Fetching appointments from Simplex")

        payload = await self._request("GET", "/appointments-by-date", params=params)
        result = SimplexAppointmentsResponse.model_validate(payload)
        if result.error_count:
            log.warning(
                "Simplex responded with non-zero error_count",
                error_count=result.error_count,
                message=result.message,
            )
        log.info("Fetched appointments from Simplex", result_count=result.result_count)
        return result

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_patient_visit_history(
        self,
        *,
        permanent_mrn_no: str,
        permanent_visit_no: str,
    ) -> SimplexPatientVisitHistoryResponse:
        # v2 endpoint is outside of /api base; pass absolute path starting with /v2
        params = {
            "permanent_mrn_no": permanent_mrn_no,
            "permanent_visit_no": permanent_visit_no,
        }
        log = logger.bind(endpoint="get-patient-visit-history")
        log.info("Fetching patient visit history from Simplex v2", endpoint="get-patient-visit-history")
        payload = await self._request("GET", "/api/v2/patient-visit-histories", params=params)
        return SimplexPatientVisitHistoryResponse.model_validate(payload)
