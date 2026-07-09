# JT-159 Company Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic company type and industry metadata so Q-24 can be answered on the dashboard.

**Architecture:** Add a local `company_profiles` support table keyed by normalized company name, expose repository DTOs for upsert/read behavior, extend deterministic metrics breakdowns with `company_type` and `industry`, and render Q-24 from those metrics. Dashboard metrics remain deterministic SQL over local SQLite and never use LLM output for counts.

**Tech Stack:** FastAPI, SQLite/Alembic, Pydantic v2, repository pattern, React/TypeScript/Vite, Orval-generated API client, Recharts-compatible dashboard panels.

---

## File Structure

- Create `backend/app/db/migrations/versions/20260709_0159_company_profiles.py` for the `company_profiles` table.
- Create `backend/app/models/company_profile.py` for company profile literals and DTOs.
- Modify `backend/app/models/__init__.py` to export company profile DTOs.
- Create `backend/app/db/repositories/company_profile.py` for upsert/read behavior.
- Modify `backend/app/db/repositories/__init__.py` to export `CompanyProfileRepository`.
- Modify `backend/app/db/repositories/metrics.py` to add `company_type` and `industry` breakdown dimensions with left joins.
- Modify `backend/app/models/metrics.py` to extend `MetricsBreakdownDimension`.
- Modify `backend/tests/test_metrics_breakdown_api.py` to cover Q-24 metrics.
- Create `backend/tests/test_company_profile_repository.py` for profile repository behavior.
- Modify `frontend/src/pages/DashboardPage.tsx` to expose company type and industry breakdowns and add a Q-24 section.
- Modify `frontend/src/pages/DashboardPage.test.tsx` and `frontend/src/App.test.tsx` for frontend behavior.
- Regenerate `frontend/src/api/openapi.json` and `frontend/src/api/generated.ts` if OpenAPI changes.
- Create `docs/tickets/JT-159.md` with behavior, why, verification, and usage notes.

---

### Task 1: Company Profile Schema And Repository

**Files:**
- Create: `backend/app/db/migrations/versions/20260709_0159_company_profiles.py`
- Create: `backend/app/models/company_profile.py`
- Create: `backend/app/db/repositories/company_profile.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/repositories/__init__.py`
- Test: `backend/tests/test_company_profile_repository.py`

- [ ] **Step 1: Write the failing repository test**

Create `backend/tests/test_company_profile_repository.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.db.repositories import CompanyProfileRepository

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_company_profile_repository_upserts_and_reads_profiles(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        repository = CompanyProfileRepository(connection)

        repository.upsert_profile(
            normalized_company="example labs",
            display_company="Example Labs",
            company_type="startup",
            industry="Developer tools",
            source="manual",
            updated_at="2026-07-09T12:00:00+00:00",
        )
        repository.upsert_profile(
            normalized_company="example labs",
            display_company="Example Labs",
            company_type="enterprise",
            industry="Cloud infrastructure",
            source="imported",
            updated_at="2026-07-09T13:00:00+00:00",
        )

        profile = repository.get_profile("example labs")

    assert profile is not None
    assert profile.normalized_company == "example labs"
    assert profile.display_company == "Example Labs"
    assert profile.company_type == "enterprise"
    assert profile.industry == "Cloud infrastructure"
    assert profile.source == "imported"


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path
```

- [ ] **Step 2: Run the failing repository test**

Run: `uv run --project backend pytest backend/tests/test_company_profile_repository.py -q`

Expected: FAIL with `ImportError` or `AttributeError` because `CompanyProfileRepository` does not exist.

- [ ] **Step 3: Add the migration**

Create `backend/app/db/migrations/versions/20260709_0159_company_profiles.py`:

```python
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260709_0159"
down_revision = "20260707_0190"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("normalized_company", sa.Text(), primary_key=True),
        sa.Column("display_company", sa.Text(), nullable=False),
        sa.Column("company_type", sa.Text(), nullable=False),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "company_type IN ('startup', 'enterprise', 'public_company', 'agency', "
            "'nonprofit', 'education', 'government', 'unknown', 'other')",
            name="ck_company_profiles_company_type",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'imported', 'extracted', 'unknown')",
            name="ck_company_profiles_source",
        ),
    )
    op.create_index(
        "ix_company_profiles_company_type",
        "company_profiles",
        ["company_type"],
    )
    op.create_index(
        "ix_company_profiles_industry",
        "company_profiles",
        ["industry"],
    )


def downgrade() -> None:
    op.drop_index("ix_company_profiles_industry", table_name="company_profiles")
    op.drop_index("ix_company_profiles_company_type", table_name="company_profiles")
    op.drop_table("company_profiles")
```

- [ ] **Step 4: Add DTOs**

Create `backend/app/models/company_profile.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

type CompanyType = Literal[
    "startup",
    "enterprise",
    "public_company",
    "agency",
    "nonprofit",
    "education",
    "government",
    "unknown",
    "other",
]
type CompanyProfileSource = Literal["manual", "imported", "extracted", "unknown"]


class CompanyProfileRecord(BaseModel):
    normalized_company: str
    display_company: str
    company_type: CompanyType
    industry: str | None
    source: CompanyProfileSource
    created_at: str
    updated_at: str
```

- [ ] **Step 5: Add repository implementation**

Create `backend/app/db/repositories/company_profile.py`:

```python
from __future__ import annotations

import sqlite3

from app.db.repositories.base import BaseRepository
from app.models.company_profile import CompanyProfileRecord, CompanyProfileSource, CompanyType


class CompanyProfileRepository(BaseRepository[CompanyProfileRecord]):
    def upsert_profile(
        self,
        *,
        normalized_company: str,
        display_company: str,
        company_type: CompanyType,
        industry: str | None,
        source: CompanyProfileSource,
        updated_at: str,
    ) -> CompanyProfileRecord:
        normalized = normalized_company.strip().lower()
        display = display_company.strip()
        self.execute(
            """
            INSERT INTO company_profiles (
                normalized_company, display_company, company_type, industry,
                source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_company) DO UPDATE SET
                display_company = excluded.display_company,
                company_type = excluded.company_type,
                industry = excluded.industry,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                normalized,
                display,
                company_type,
                industry.strip() if industry is not None else None,
                source,
                updated_at,
                updated_at,
            ),
        )
        self.connection.commit()
        profile = self.get_profile(normalized)
        if profile is None:
            msg = f"Company profile was not persisted: {normalized}"
            raise RuntimeError(msg)
        return profile

    def get_profile(self, normalized_company: str) -> CompanyProfileRecord | None:
        row = self.execute(
            """
            SELECT normalized_company, display_company, company_type, industry,
                source, created_at, updated_at
            FROM company_profiles
            WHERE normalized_company = ?
            """,
            (normalized_company.strip().lower(),),
        ).fetchone()
        if row is None:
            return None
        return self.map_row(row)

    def map_row(self, row: sqlite3.Row) -> CompanyProfileRecord:
        return CompanyProfileRecord(
            normalized_company=str(row["normalized_company"]),
            display_company=str(row["display_company"]),
            company_type=row["company_type"],
            industry=None if row["industry"] is None else str(row["industry"]),
            source=row["source"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
```

- [ ] **Step 6: Export DTOs and repository**

Add these imports and `__all__` entries in `backend/app/models/__init__.py`:

```python
from .company_profile import CompanyProfileRecord, CompanyProfileSource, CompanyType
```

Add these names to `__all__`:

```python
"CompanyProfileRecord",
"CompanyProfileSource",
"CompanyType",
```

Add this import in `backend/app/db/repositories/__init__.py`:

```python
from .company_profile import CompanyProfileRepository
```

Add this name to `__all__`:

```python
"CompanyProfileRepository",
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run --project backend pytest backend/tests/test_company_profile_repository.py -q`

Expected: PASS.

- [ ] **Step 8: Commit task 1**

Run:

```bash
git add backend/app/db/migrations/versions/20260709_0159_company_profiles.py backend/app/models/company_profile.py backend/app/models/__init__.py backend/app/db/repositories/company_profile.py backend/app/db/repositories/__init__.py backend/tests/test_company_profile_repository.py
git commit -m "feat: add company profiles"
```

### Task 2: Company Type And Industry Metrics Breakdowns

**Files:**
- Modify: `backend/app/models/metrics.py`
- Modify: `backend/app/db/repositories/metrics.py`
- Test: `backend/tests/test_metrics_breakdown_api.py`

- [ ] **Step 1: Write failing API tests**

Add tests to `backend/tests/test_metrics_breakdown_api.py`:

```python
def test_metrics_breakdown_returns_company_type_rows(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_company_profile(connection, "startup corp", "startup", "Devtools")
        insert_company_profile(connection, "enterprise inc", "enterprise", "Cloud")
        insert_application_with_events(connection, "app-startup", "linkedin", ("applied", "response"), company="Startup Corp")
        insert_application_with_events(connection, "app-enterprise", "company_site", ("applied",), company="Enterprise Inc")
        insert_application_with_events(connection, "app-unknown", "referral", ("applied", "interview_scheduled"), company="Mystery LLC")

    response = create_test_client(database_path).get("/metrics/breakdown?dimension=company_type")

    assert response.status_code == 200
    assert response.json()["dimension"] == "company_type"
    assert response.json()["rows"] == [
        {"dimension": "company_type", "value": "enterprise", "application_count": 1, "response_count": 0, "interview_count": 0, "offer_count": 0},
        {"dimension": "company_type", "value": "startup", "application_count": 1, "response_count": 1, "interview_count": 0, "offer_count": 0},
        {"dimension": "company_type", "value": "unknown", "application_count": 1, "response_count": 1, "interview_count": 1, "offer_count": 0},
    ]


def test_metrics_breakdown_returns_industry_rows(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_company_profile(connection, "startup corp", "startup", "Devtools")
        insert_application_with_events(connection, "app-startup", "linkedin", ("applied", "response"), company="Startup Corp")
        insert_application_with_events(connection, "app-unknown", "referral", ("applied",), company="Mystery LLC")

    response = create_test_client(database_path).get("/metrics/breakdown?dimension=industry")

    assert response.status_code == 200
    assert response.json()["dimension"] == "industry"
    assert response.json()["rows"] == [
        {"dimension": "industry", "value": "devtools", "application_count": 1, "response_count": 1, "interview_count": 0, "offer_count": 0},
        {"dimension": "industry", "value": "unknown", "application_count": 1, "response_count": 0, "interview_count": 0, "offer_count": 0},
    ]
```

Add helper in the same file:

```python
def insert_company_profile(
    connection: sqlite3.Connection,
    normalized_company: str,
    company_type: str,
    industry: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO company_profiles (
            normalized_company, display_company, company_type, industry,
            source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_company,
            normalized_company.title(),
            company_type,
            industry,
            "manual",
            "2026-07-09T12:00:00+00:00",
            "2026-07-09T12:00:00+00:00",
        ),
    )
```

If `insert_application_with_events` does not accept `company`, add an optional `company: str | None = None` parameter and pass `company or f"{application_id} Corp"` into `ApplicationRepository.upsert_application`.

- [ ] **Step 2: Run failing API tests**

Run: `uv run --project backend pytest backend/tests/test_metrics_breakdown_api.py -q`

Expected: FAIL because `company_type` and `industry` are not valid breakdown dimensions.

- [ ] **Step 3: Extend breakdown dimension type**

Modify `backend/app/models/metrics.py` so `MetricsBreakdownDimension` includes:

```python
"company_type",
"industry",
```

- [ ] **Step 4: Add SQL dimensions**

Modify `backend/app/db/repositories/metrics.py`.

In `_dimension_expression`, add:

```python
if dimension == "company_type":
    return "COALESCE(NULLIF(company_profiles.company_type, ''), 'unknown')"
if dimension == "industry":
    return "COALESCE(NULLIF(LOWER(TRIM(company_profiles.industry)), ''), 'unknown')"
```

In `_get_application_breakdown`, add the left join before `{where_clause}`:

```sql
LEFT JOIN company_profiles
    ON company_profiles.normalized_company = LOWER(TRIM(applications.company))
```

Keep existing filter parameters in the same order.

- [ ] **Step 5: Run API tests to verify pass**

Run: `uv run --project backend pytest backend/tests/test_metrics_breakdown_api.py -q`

Expected: PASS.

- [ ] **Step 6: Commit task 2**

Run:

```bash
git add backend/app/models/metrics.py backend/app/db/repositories/metrics.py backend/tests/test_metrics_breakdown_api.py
git commit -m "feat: add company metadata breakdowns"
```

### Task 3: Dashboard Q-24 Presentation

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.test.tsx`
- Modify: `frontend/src/App.test.tsx`
- Generated if changed: `frontend/src/api/openapi.json`, `frontend/src/api/generated.ts`

- [ ] **Step 1: Regenerate frontend API after backend type change**

Run: `npm --prefix frontend run generate:api`

Expected: generated API includes `company_type` and `industry` enum values for `MetricsBreakdownDimension`.

- [ ] **Step 2: Write failing dashboard test**

Add a mock response in `frontend/src/pages/DashboardPage.test.tsx`:

```typescript
if (url === "/metrics/breakdown?dimension=company_type") {
  return Promise.resolve(
    new Response(
      JSON.stringify({
        dimension: "company_type",
        rows: [
          {
            application_count: 3,
            dimension: "company_type",
            interview_count: 1,
            offer_count: 0,
            response_count: 2,
            value: "startup",
          },
          {
            application_count: 2,
            dimension: "company_type",
            interview_count: 0,
            offer_count: 0,
            response_count: 0,
            value: "enterprise",
          },
        ],
      }),
      { headers: { "Content-Type": "application/json" }, status: 200 },
    ),
  );
}
```

Add test:

```typescript
it("renders Q-24 company type outcomes", async () => {
  const fetchMock = mockApplicationResponses();
  window.history.pushState({}, "", "/dashboard");

  render(<DashboardPage />);

  const companyTypes = await screen.findByRole("region", {
    name: "Company type outcomes",
  });

  expect(within(companyTypes).getByText("Startup")).toBeTruthy();
  expect(within(companyTypes).getByText("2 responses")).toBeTruthy();
  expect(within(companyTypes).getByText("1 interview")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith(
    "/metrics/breakdown?dimension=company_type",
    expect.objectContaining({ method: "GET" }),
  );
});
```

- [ ] **Step 3: Run failing dashboard test**

Run: `npm --prefix frontend run test -- src/pages/DashboardPage.test.tsx`

Expected: FAIL because `Company type outcomes` region does not exist.

- [ ] **Step 4: Add Q-24 dashboard state and loader**

In `frontend/src/pages/DashboardPage.tsx`, add state near existing breakdown state:

```typescript
const [companyTypeRows, setCompanyTypeRows] = useState<MetricBreakdownRow[]>([]);
const [companyTypeLoadState, setCompanyTypeLoadState] =
  useState<BreakdownLoadState>("loading");
const [companyTypeError, setCompanyTypeError] = useState<string | null>(null);
```

Add effect:

```typescript
useEffect(() => {
  let isCancelled = false;

  async function loadCompanyTypes() {
    setCompanyTypeLoadState("loading");
    setCompanyTypeError(null);
    setCompanyTypeRows([]);

    const response = await getMetricsBreakdownMetricsBreakdownGet({
      dimension: MetricsBreakdownDimension.company_type,
      ...queryParamsFromFilters(appliedFilters),
    });

    if (isCancelled) {
      return;
    }

    if (response.status !== 200) {
      setCompanyTypeRows([]);
      setCompanyTypeError(
        publicError(response.data, "Company type outcomes are unavailable."),
      );
      setCompanyTypeLoadState("error");
      return;
    }

    setCompanyTypeRows(sortedBreakdownRows(response.data.rows));
    setCompanyTypeLoadState("loaded");
  }

  void loadCompanyTypes().catch(() => {
    if (!isCancelled) {
      setCompanyTypeRows([]);
      setCompanyTypeError(
        "Company type outcomes are unavailable. Start the local backend to load Q-24.",
      );
      setCompanyTypeLoadState("error");
    }
  });

  return () => {
    isCancelled = true;
  };
}, [appliedFilters]);
```

- [ ] **Step 5: Add Q-24 section**

Add section after best-converting titles:

```tsx
<section
  aria-labelledby="company-type-outcomes-title"
  className="dashboard-card dashboard-breakdown-card"
>
  <div>
    <p className="eyebrow">Q-24</p>
    <h2 id="company-type-outcomes-title">Company type outcomes</h2>
    <p className="dashboard-card__meta">
      Company type outcomes come from deterministic company profile metadata joined to applications.
    </p>
  </div>

  {companyTypeError ? (
    <Alert title="Company type outcomes unavailable" tone="danger">
      <p>{companyTypeError}</p>
    </Alert>
  ) : null}

  <ol className="dashboard-breakdown-ranks">
    {companyTypeRows.length > 0 ? (
      companyTypeRows.slice(0, 5).map((row) => (
        <li key={`${row.dimension}-${row.value}`}>
          <div>
            <span className="dashboard-breakdown-rank__label">
              {titleize(row.value)}
            </span>
            <span>{countLabel(row.application_count, "application")}</span>
          </div>
          <p>
            {countLabel(row.response_count, "response")}, {countLabel(row.interview_count, "interview")}, {countLabel(row.offer_count, "offer")}
          </p>
        </li>
      ))
    ) : (
      <li>
        <div>
          <span className="dashboard-breakdown-rank__label">
            {companyTypeLoadState === "loading" ? "Loading" : "No rows"}
          </span>
          <span>
            {companyTypeLoadState === "loading"
              ? "Fetching company types"
              : "No company type data"}
          </span>
        </div>
      </li>
    )}
  </ol>
</section>
```

- [ ] **Step 6: Add App test fallback**

In `frontend/src/App.test.tsx`, add default mock for `/metrics/breakdown?dimension=company_type`:

```typescript
if (path === "/metrics/breakdown?dimension=company_type") {
  return Promise.resolve(
    new Response(JSON.stringify(metricsBreakdownResponse({ dimension: "company_type" })), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
}
```

Update exact fetch-order expectations to include `/metrics/breakdown?dimension=company_type` where the dashboard route loads all sections.

- [ ] **Step 7: Run frontend tests**

Run: `npm --prefix frontend run test -- src/pages/DashboardPage.test.tsx`

Expected: PASS.

- [ ] **Step 8: Commit task 3**

Run:

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/pages/DashboardPage.test.tsx frontend/src/App.test.tsx frontend/src/api/openapi.json frontend/src/api/generated.ts
git commit -m "feat: show company type outcomes"
```

### Task 4: Ticket Documentation And Final Verification

**Files:**
- Create: `docs/tickets/JT-159.md`

- [ ] **Step 1: Create ticket documentation**

Create `docs/tickets/JT-159.md`:

```markdown
# JT-159 - Company Type Conversion

## What Changed

Added local company profile metadata for deterministic company type and industry segmentation.
Extended metrics breakdowns with `company_type` and `industry` dimensions.
Added a Q-24 dashboard section showing company type outcomes for active filters.

## Why

Q-24 asks which company types or industries respond best.
Dashboard counts must come from deterministic local data, so company metadata is stored before metrics use it.

## Verification

Run from the repository root:

```sh
uv run --project backend ruff check backend
uv run --project backend pytest backend/tests/test_company_profile_repository.py backend/tests/test_metrics_breakdown_api.py -q
```

Run from `backend/`:

```sh
uv run mypy
```

Run from the repository root:

```sh
npm --prefix frontend run check
```

## Usage Notes

Company type and industry breakdowns use `company_profiles` rows joined to applications by normalized company name.
Applications without company metadata are grouped as `unknown`.
```

- [ ] **Step 2: Run backend verification**

Run:

```bash
uv run --project backend ruff check backend
uv run --project backend pytest backend/tests/test_company_profile_repository.py backend/tests/test_metrics_breakdown_api.py -q
```

Expected: both commands pass.

- [ ] **Step 3: Run backend type checking**

Run from `backend/`: `uv run mypy`

Expected: PASS.

- [ ] **Step 4: Run frontend verification**

Run: `npm --prefix frontend run check`

Expected: PASS. Vite may emit the existing non-failing large chunk warning.

- [ ] **Step 5: Commit documentation and final fixes**

Run:

```bash
git add docs/tickets/JT-159.md
git commit -m "docs: document JT-159 company type outcomes"
```

- [ ] **Step 6: Push and open PR**

Run:

```bash
git push -u origin jt-159-company-metadata-design
gh pr create --repo talibilat/job-search-intelligence --base main --head jt-159-company-metadata-design --title "JT-159: Answer company type conversion" --body "## Summary
- Add local company profile metadata for deterministic company type and industry segmentation.
- Extend metrics breakdowns with company_type and industry dimensions.
- Render Q-24 company type outcomes on the dashboard.

## Verification
- uv run --project backend ruff check backend
- uv run --project backend pytest backend/tests/test_company_profile_repository.py backend/tests/test_metrics_breakdown_api.py -q
- (from backend/) uv run mypy
- npm --prefix frontend run check"
```

Expected: PR URL is printed.

---

## Self-Review Notes

Spec coverage: the plan covers schema, DTOs, repository, deterministic metrics, frontend Q-24 display, unknown bucketing, filters, and verification.

Placeholder scan: no TODO, TBD, or unspecified implementation steps remain.

Type consistency: `CompanyProfileRecord`, `CompanyProfileRepository`, `company_type`, `industry`, and `MetricsBreakdownDimension` names match across tasks.
