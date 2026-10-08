"""Book import from CSV: column detection, row checks, client matching, duplicates, one transaction."""

import httpx

from tests.support import Org

CSV = """Insured Name,Mobile,Email,Insurance Company,Cover Type,Policy No,Reg No,Inception Date,Expiry Date,Gross Premium,Comm %,Basic Premium
Otieno Ochieng,0711 000 777,,Savanna General,Motor - Comprehensive,SG/MP/001,KDA 123A,01/03/2026,28/02/2027,"KES 38,500",10%,"38,300"
Otieno Ochieng,0711 000 777,,Rift Assurance,Medical,RA/MED/9,Family medical,15/01/2026,14/01/2027,60000,,
Acacia Traders Ltd,0722 111 222,info@acacia.example.com,Savanna General,WIBA,SG/WIBA/7,Staff WIBA,01/07/2026,30/06/2027,25000,,
Mary,0733 333 333,,Savanna General,Motor,SG/MP/002,KCB 789C,2026-02-30,,12000,,
Peter Kamau,0744 444 444,,Savanna General,Space tourism,SG/X/1,Rocket,01/01/2026,,5000,,
Existing Client,0755 555 555,,Savanna General,Motor,SG/OLD/1,KCC 111C,01/01/2026,,9000,,
"""


async def test_import_book_from_csv(api: httpx.AsyncClient, ready_org: Org) -> None:
    h = ready_org.headers()
    otieno = (
        await api.post(
            "/api/v1/clients",
            json={"first_name": "Otieno", "last_name": "Ochieng", "phone": "+254711000777"},
            headers=h,
        )
    ).json()
    old = await api.post(
        "/api/v1/policies",
        json={
            "client_id": otieno["id"],
            "insurer_name": "Savanna General",
            "class_code": "motor_private",
            "policy_number": "SG/OLD/1",
            "start_date": "2026-01-01",
            "total_premium": "9000",
        },
        headers=h,
    )
    assert old.status_code == 201

    body = {"filename": "my book.csv", "csv": CSV}
    preview = (await api.post("/api/v1/imports/policies/preview", json=body, headers=h)).json()
    assert preview["problems"] == []
    assert preview["mapping"]["client_name"] == "Insured Name"
    assert preview["mapping"]["basic_premium"] == "Basic Premium"
    by_line = {r["line"]: r for r in preview["rows"]}
    assert by_line[2]["status"] == "ok"
    assert by_line[2]["client_action"] == "match"  # same phone as an existing client
    assert by_line[2]["class_code"] == "motor_private"
    assert by_line[2]["premium"] == "38500"
    assert by_line[4]["client_action"] == "create"
    assert by_line[4]["class_code"] == "wiba"
    assert by_line[5]["status"] == "error"
    assert any("first and last name" in m for m in by_line[5]["messages"])
    assert any("Cannot read the date" in m for m in by_line[5]["messages"])
    assert any("Unknown class" in m for m in by_line[6]["messages"])
    assert by_line[7]["status"] == "skip"
    assert (preview["ok"], preview["errors"], preview["skipped"]) == (3, 2, 1)
    assert (preview["new_clients"], preview["matched_clients"]) == (1, 1)

    refused = await api.post("/api/v1/imports/policies", json=body, headers=h)
    assert refused.json()["code"] == "import_invalid"
    result = await api.post(
        "/api/v1/imports/policies", json=body | {"skip_errors": True}, headers=h
    )
    assert result.status_code == 201, result.text
    assert result.json() | {"import_id": None} == {
        "import_id": None,
        "clients_created": 1,
        "clients_matched": 1,
        "policies_created": 3,
        "rows_skipped": 3,
    }

    policies = (await api.get("/api/v1/policies", params={"q": "SG/MP/001"}, headers=h)).json()
    motor = (await api.get(f"/api/v1/policies/{policies[0]['id']}", headers=h)).json()
    assert motor["client"]["id"] == otieno["id"]
    assert motor["status"] == "active"
    assert motor["activation"]["basis"] == "imported"
    assert motor["activation"]["import"] == result.json()["import_id"]
    assert motor["payments"][0]["reference"] == "Opening balance (import)"
    assert motor["balance"] == "0.00"
    assert motor["commission"]["gross"] == "3830.00"
    assert motor["end_date"] == "2027-02-28"
    clients = (await api.get("/api/v1/clients", params={"q": "Acacia"}, headers=h)).json()
    assert clients["items"][0]["kind"] == "corporate"

    # Importing the same file again creates nothing.
    second = await api.post(
        "/api/v1/imports/policies", json=body | {"skip_errors": True}, headers=h
    )
    assert second.json()["code"] == "import_invalid"


async def test_mapping_problems_and_unpaid(api: httpx.AsyncClient, ready_org: Org) -> None:
    h = ready_org.headers()
    csv = "Customer,Underwriter,Line,Start,Amount\nJane Wairimu,Savanna General,Home,01/02/2026,8000\n"
    preview = (
        await api.post(
            "/api/v1/imports/policies/preview",
            json={"filename": "x.csv", "csv": csv, "mapping": {"client_name": "Customer"}},
            headers=h,
        )
    ).json()
    assert "Choose the column for Insurer" in preview["problems"]
    mapping = {
        "client_name": "Customer",
        "insurer": "Underwriter",
        "class": "Line",
        "start_date": "Start",
        "premium": "Amount",
    }
    done = await api.post(
        "/api/v1/imports/policies",
        json={"filename": "x.csv", "csv": csv, "mapping": mapping, "assume_paid": False},
        headers=h,
    )
    assert done.status_code == 201, done.text
    home = (await api.get("/api/v1/policies", params={"q": "Savanna"}, headers=h)).json()[0]
    assert home["balance"] == "8000.00"
    assert home["status"] == "active"
    viewer = ready_org.headers("viewer")
    await api.get("/api/v1/me", headers=viewer)
    assert (
        await api.post(
            "/api/v1/imports/policies/preview",
            json={"filename": "x.csv", "csv": csv},
            headers=viewer,
        )
    ).status_code == 403
