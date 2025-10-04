# Yma Anonymization Middleware

A FastAPI service that anonymizes medical data using **MedGemma** model running on **Super Protocol's Confidential Computing** platform.

Super Protocol provides secure data processing using Intel SGX technology and Trusted Execution Environments (TEE), ensuring that medical data remains confidential even during processing. This means your sensitive medical data is protected from unauthorized access, including cloud providers and infrastructure owners.

The service can anonymize text directly or fetch patient visit history from Simplex EHR system and anonymize it automatically.

## Quick Start

### Option 1: Using Docker

Build and run the Docker container:

```bash
docker build -t yma-anonymizer .
docker run -p 8000:8000 --env-file .env yma-anonymizer
```

### Option 2: Using start_linux.sh

Run the startup script (creates venv, installs dependencies, and starts the server):

```bash
./start_linux.sh
```

The API will be available at `http://localhost:8000`

## Environment Variables

Create a `.env` file in the project root using `.env.template`

## API Endpoints

- `GET /healthz` - Health check
- `POST /anonymize` - Anonymize any text data
- `GET /ehr/patient-visit-histories` - Fetch and anonymize patient visit history from Simplex

