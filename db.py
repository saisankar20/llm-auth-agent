import os, json, psycopg

DSN = os.getenv("DB_DSN", "postgresql://observability:changeme@postgres:5432/observability")

async def get_conn():
    return await psycopg.AsyncConnection.connect(DSN)

async def upsert_credentials(site_id, username, password):
    async with await get_conn() as con:
        await con.execute(
            "INSERT INTO auth.credentials(site_id,username,password) VALUES (%s,%s,%s)",
            (site_id, username, password)
        )

async def insert_token(site_id, kind, token, cookies, expires_at):
    async with await get_conn() as con:
        await con.execute(
            "INSERT INTO auth.tokens(site_id,kind,token,cookies,expires_at) VALUES (%s,%s,%s,%s,%s)",
            (site_id, kind, token, json.dumps(cookies or {}), expires_at)
        )

async def latest_token(site_id):
    async with await get_conn() as con:
        cur = await con.execute(
            "SELECT kind, token, cookies FROM auth.tokens WHERE site_id=%s ORDER BY id DESC LIMIT 1",
            (site_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        kind, token, cookies = row
        return {"kind": kind, "token": token, "cookies": cookies}

async def record_telemetry(site_id, endpoint, status, latency_ms):
    async with await get_conn() as con:
        await con.execute(
            "INSERT INTO auth.telemetry(site_id,endpoint,status,latency_ms) VALUES (%s,%s,%s,%s)",
            (site_id, endpoint, status, latency_ms)
        )
