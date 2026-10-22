# CivicLens — Intelligent Public Infrastructure Complaint Management System

CivicLens is a web-based platform designed to simplify the reporting and management of public infrastructure problems such as potholes, damaged roads, broken streetlights, drainage issues, and waste accumulation.

The system connects citizens with municipal authorities through a common platform where complaints can be reported, monitored, prioritized, and resolved efficiently.

## Overview

CivicLens goes beyond traditional complaint management by using intelligent duplicate detection, automated priority scoring, and incident tracking.

Citizens can submit complaints with descriptions, photographs, and precise locations. The system identifies similar complaints using text similarity, geographic proximity, and image comparison, grouping related reports under a common incident.

Each incident receives a priority based on its severity, public impact, number of independent reports, and time unresolved. Authorities can then assign incidents to appropriate departments and officers, monitor repair progress, and verify completed work through citizen feedback.

## Key Features

- **Complaint Reporting:** Submit infrastructure issues with descriptions, photographs, and locations.
- **Intelligent Duplicate Detection:** Identify similar complaints using text, image, and location analysis.
- **Incident Clustering:** Group related complaints while preserving individual reports.
- **Dynamic Priority Scoring:** Rank issues based on severity, impact, public reports, and unresolved time.
- **Interactive Maps:** Locate reported issues using category-specific markers and search within a 200 km radius.
- **Department and Officer Assignment:** Route incidents to relevant departments and track assigned work.
- **Repair Verification:** Allow officers to submit repair evidence and citizens to provide feedback.
- **Recurring Issue Detection:** Identify infrastructure problems that reappear after repairs.
- **Automated Workflows:** Process complaints, update incident information, and generate notifications.
- **Administrative Dashboard:** Monitor incidents, department performance, geographic hotspots, and resolution progress.
- **Role-Based Access:** Separate interfaces and permissions for citizens, officers, and administrators.

## Technology Stack

**Frontend:** React, TypeScript, Vite, Tailwind CSS

**Backend:** Python, FastAPI

**Database:** SQLite (local development)

**Machine Learning:** Scikit-learn, TF-IDF, Cosine Similarity, Perceptual Image Hashing

**Maps:** Leaflet, React Leaflet, OpenStreetMap

**Testing:** Pytest, Vitest, Playwright

## Project Structure

```text
CivicLens/
├── frontend/        # React frontend application
├── backend/         # FastAPI backend and application logic
├── infrastructure/  # Infrastructure configuration
├── scripts/         # Setup, execution and testing scripts
├── tests/           # Integration tests
└── docs/            # Technical documentation
```

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js (Vite-compatible version)
- Git

### Installation

Clone the repository:

```powershell
git clone https://github.com/shaun031/CivicLens.git
cd CivicLens
```

Install dependencies:

```powershell
.\scripts\setup.ps1
```

### Run the Application

Start the backend:

```powershell
.\scripts\run-backend.ps1
```

Start the frontend in another terminal:

```powershell
.\scripts\run-frontend.ps1
```

Start the background event worker in a separate terminal:

```powershell
.\scripts\run-worker.ps1
```

Open the application at:

**http://localhost:5173**

Backend API documentation:

**http://127.0.0.1:8000/docs**

### Run Tests

```powershell
.\scripts\verify.ps1
```

## Expected Outcome

CivicLens aims to make public infrastructure maintenance more organized, transparent, and efficient. By combining intelligent complaint analysis, automated incident management, interactive maps, and citizen participation, the platform helps municipal authorities identify important problems, reduce duplicate work, and track resolution efforts more effectively.