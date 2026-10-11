from fastapi.testclient import TestClient
from app.main import app

AOI_OK = {"type": "Polygon", "coordinates": [[[77.45, 8.68], [77.52, 8.68], [77.52, 8.73], [77.45, 8.73], [77.45, 8.68]]]}
AOI_SMALL = {"type": "Polygon", "coordinates": [[[77.45, 8.68], [77.47, 8.68], [77.47, 8.70], [77.45, 8.70], [77.45, 8.68]]]}


def test_small_area_rejected():
    with TestClient(app) as c:
        r = c.post("/analysis", json={"aoi": AOI_SMALL})
        assert r.status_code == 422 and "20" in r.json()["detail"]


def test_full_flow():
    with TestClient(app) as c:
        r = c.post("/analysis", json={"aoi": AOI_OK, "name": "t"})
        assert r.status_code == 200
        jid = r.json()["job_id"]
        assert c.get(f"/analysis/{jid}").json()["status"] == "done"
        fc = c.get("/parcels", params={"job_id": jid, "year": 2026}).json()
        assert len(fc["features"]) > 100
        assert max(f["properties"]["confidence"] for f in fc["features"]) <= 0.97
        st = c.get("/statistics", params={"job_id": jid}).json()["stats"]
        assert st["total_parcels"] == len(fc["features"])
        ch = c.get("/change-detection", params={"job_id": jid, "period_a": 2025, "period_b": 2026}).json()
        assert "summary" in ch
        assert "answer" in c.post("/chat", json={"job_id": jid, "message": "Which crop occupies the largest area?"}).json()
        assert c.get("/export", params={"job_id": jid, "format": "csv"}).status_code == 200
        assert c.get("/export", params={"job_id": jid, "format": "pdf"}).headers["content-type"] == "application/pdf"
