"""
Telegram Analyst Bot — Multi-Agent Sector Specialist
พิมพ์ถามใน Telegram → Orchestrator เลือก Specialist → ตอบกลับ
รองรับ 8 sectors: Banking, Energy, Property, ICT, Healthcare, Consumer, Industrial, Tourism
"""

import asyncio
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

# ── Config ──────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID    = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]

BANGKOK_TZ          = ZoneInfo("Asia/Bangkok")
MODEL_ORCHESTRATOR  = "claude-haiku-4-5-20251001"   # เร็ว ประหยัด สำหรับ routing
MODEL_SPECIALIST    = "claude-sonnet-4-6"            # ฉลาด สำหรับวิเคราะห์

POLL_INTERVAL_SEC   = 3   # poll Telegram ทุก 3 วินาที

# ── Sector Mapping ──────────────────────────────────────────────────────
SECTOR_MAP = {
    # Banking & Finance
    "BANKING": ["KBANK","SCB","BBL","KTB","BAY","TTB","TISCO","KKP","MTC",
                "SAWAD","TIDLOR","JMT","AEONTS","KTC","TCAP","THANI"],
    # Energy & Commodity
    "ENERGY":  ["PTT","PTTEP","PTTGC","TOP","IRPC","BCP","SPRC","EGCO",
                "GULF","RATCH","GPSC","BGRIM","EA","GUNKUL","CKP"],
    # Property & Construction
    "PROPERTY":["LH","AP","SIRI","ORI","PSH","QH","SPALI","CPN","AWC",
                "WHA","AMATA","STEC","CK","ITD","NWR"],
    # Technology & ICT
    "ICT":     ["ADVANC","TRUE","INTUCH","DELTA","HANA","KCE","SVI",
                "FORTH","MFEC","NETBAY","COM7","SYNEX"],
    # Healthcare & Hospital
    "HEALTH":  ["BDMS","BH","CHG","BCH","RJH","VIBHA","PR9","RAM",
                "CHKP","WPH","NHP"],
    # Consumer & Retail
    "CONSUMER":["CPALL","HMPRO","BJC","CRC","ROBINS","MAKRO","OSP",
                "CBG","OISHI","ICHI","TKN","SAPPE","BEAUTY"],
    # Industrial & Manufacturing
    "INDUSTRIAL":["SCC","SCCC","TU","CPF","GFPT","TVO","IVL","TASCO",
                  "TOA","DCC","PYLON","SYNTEC","SEAFCO"],
    # Tourism & Airline
    "TOURISM": ["AOT","AAV","BA","THAI","CENTEL","MINT","ERW","SHANG",
                "SHR","MAJOR","RS","VGI"],
}

# Technical Analysis agent types
TECHNICAL_AGENTS = ["TREND", "MOMENTUM", "VOLUME", "PATTERN", "CONFLUENCE"]

# สร้าง reverse map: ticker → sector
TICKER_SECTOR = {}
for sector, tickers in SECTOR_MAP.items():
    for t in tickers:
        TICKER_SECTOR[t] = sector

# ── Sector System Prompts ───────────────────────────────────────────────
SECTOR_PROMPTS = {
    "BANKING": """คุณเป็น Senior Banking Analyst ที่เชี่ยวชาญธนาคารและสถาบันการเงินในตลาดหุ้นไทย
KPIs ที่คุณวิเคราะห์เสมอ: NIM, NPL Ratio, Coverage Ratio, LDR, CAR, Cost-to-Income, ROE, Cost of Fund
Drivers: ทิศทางดอกเบี้ย BOT, Credit cycle, Loan growth, Fee income, Digital transformation
Valuation: P/BV (0.8-1.5x ปกติ), P/E (8-12x), Dividend Yield
Red Flags: NPL >3%, Coverage <150%, LDR >100%, NIM compression ในดอกเบี้ยขาขึ้น
ตอบเป็นภาษาไทย กระชับ มีตัวเลขรองรับ และสรุป Buy/Hold/Sell พร้อมเหตุผลเสมอ""",

    "ENERGY": """คุณเป็น Senior Energy Analyst เชี่ยวชาญน้ำมัน ก๊าซ และพลังงานทดแทนในตลาดไทย
KPIs: Crack Spread, Refinery Margin, Reserve Replacement Ratio, Production Volume (BOED), EBITDA/BOE, Utilization Rate
Drivers: ราคาน้ำมัน Brent/Dubai, Crack spread, USD/THB, LNG price, Capex cycle
Sensitivity: วิเคราะห์ผลกระทบทุก $10 ต่อ barrel ต่อ EPS เสมอ
Valuation: EV/EBITDA 4-7x (E&P), 6-9x (Integrated)
Red Flags: Crack spread ลบ, Reserve depletion โดยไม่มี replacement, Capex หยุด
ตอบเป็นภาษาไทย กระชับ มีตัวเลข sensitivity และสรุป Buy/Hold/Sell""",

    "PROPERTY": """คุณเป็น Senior Property Analyst เชี่ยวชาญอสังหาริมทรัพย์และก่อสร้างในตลาดไทย
KPIs: Presales, Backlog, Transfer Rate, Gross Margin, Net Gearing, Land Bank Value
Drivers: ดอกเบี้ยสินเชื่อบ้าน, นโยบาย LTV ธปท., Presales trend, Location mix, Construction cost
Valuation: P/BV 0.5-1.5x, EV/EBITDA 6-10x, Discount to NAV 20-40%
Red Flags: Presales ลบ 2Q ติดต่อกัน, Transfer rate <70%, Net gearing >2.5x
ตอบเป็นภาษาไทย กระชับ เน้น Presales vs Backlog และสรุป Buy/Hold/Sell""",

    "ICT": """คุณเป็น Senior TMT Analyst เชี่ยวชาญ Telecom, Technology, Electronics ในตลาดไทย
KPIs Telecom: ARPU, Churn Rate, Subscriber growth, EBITDA Margin 35-45%, Capex/Revenue, Net Debt/EBITDA
KPIs Electronics: Revenue/Employee, Gross Margin, Customer Concentration, Order Backlog, FX Sensitivity
Drivers: 5G penetration, Data consumption, Enterprise growth, AI/Cloud adoption, USD/THB
Red Flags: ARPU ลด + Churn เพิ่มพร้อมกัน, Customer concentration >30%
ตอบเป็นภาษาไทย กระชับ แยก Telecom vs Electronics ชัดเจน สรุป Buy/Hold/Sell""",

    "HEALTH": """คุณเป็น Senior Healthcare Analyst เชี่ยวชาญโรงพยาบาลและธุรกิจสุขภาพในตลาดไทย
KPIs: Occupancy Rate >70%, ALOS, Revenue per Bed, IP/OP Mix, EBITDA Margin 20-30%, SSRG
Drivers: Medical tourism, Aging society, Insurance penetration, Doctor recruitment, Branch expansion
Valuation: EV/EBITDA 15-25x, P/E 25-40x, EV/Bed (เทียบ peer)
Red Flags: Occupancy <60%, Doctor turnover สูง, Medical malpractice, Cost > Revenue growth
ตอบเป็นภาษาไทย กระชับ เน้น Occupancy trend และ Medical tourism สรุป Buy/Hold/Sell""",

    "CONSUMER": """คุณเป็น Senior Consumer Analyst เชี่ยวชาญค้าปลีก อาหาร เครื่องดื่มในตลาดไทย
KPIs: SSSG, Total Revenue Growth, Gross Margin 25-40%, Inventory Turnover, SG&A/Revenue, Net Cash Cycle
Drivers: Consumer confidence, เงินเฟ้อ vs basket size, E-commerce disruption, Store expansion, Private label
Red Flags: SSSG ลบ 2Q ติดต่อกัน, Inventory days เพิ่มเร็ว, Gross margin compression
Valuation: EV/EBITDA 8-15x, P/E 15-25x
ตอบเป็นภาษาไทย กระชับ เน้น SSSG trend และ margin outlook สรุป Buy/Hold/Sell""",

    "INDUSTRIAL": """คุณเป็น Senior Industrial Analyst เชี่ยวชาญอุตสาหกรรม การผลิต วัสดุในตลาดไทย
KPIs: Utilization Rate >80%, Order Backlog, Gross Margin vs RM Cost, Revenue/Employee, Capex/Depreciation, FCF
Drivers: Global trade cycle, ราคาวัตถุดิบ (steel/plastic/chemical), USD/THB สำหรับ exporter, Order intake
Red Flags: Utilization <70%, Backlog ลด 3Q ติดต่อกัน, RM cost > selling price, Capex หยุดกะทันหัน
Valuation: EV/EBITDA 6-10x, P/E 10-18x
ตอบเป็นภาษาไทย กระชับ เน้น Utilization + Order trend สรุป Buy/Hold/Sell""",

    "TOURISM": """คุณเป็น Senior Tourism & Airline Analyst เชี่ยวชาญท่องเที่ยว สายการบิน โรงแรมในตลาดไทย
KPIs Airline: Load Factor >80%, RASK, CASK, Yield, ASK/RPK growth, Fuel Cost/Total Cost 25-35%
KPIs Hotel: RevPAR, Occupancy >70%, ADR, Tourist Arrivals
Drivers: จำนวนนักท่องเที่ยวต่างชาติ, Jet Fuel price, USD/THB, Route expansion, Low-cost competition
Red Flags: Load factor <75%, CASK > RASK, Net debt พุ่งใน demand ต่ำ, RevPAR ลดใน high season
Valuation: EV/EBITDAR 5-8x airline, EV/EBITDA 8-15x hotel
ตอบเป็นภาษาไทย กระชับ เน้น Tourist arrival trend และ yield สรุป Buy/Hold/Sell""",

    "GENERAL": """คุณเป็น Senior Investment Analyst ที่เชี่ยวชาญตลาดหุ้นไทยและต่างประเทศ
วิเคราะห์ครบทั้ง Fundamental และ Technical Analysis
ตอบเป็นภาษาไทย กระชับ มีตัวเลขรองรับ และสรุป Buy/Hold/Sell พร้อมเหตุผลเสมอ
ถ้าไม่มีข้อมูลเพียงพอ ให้บอกว่าต้องการข้อมูลอะไรเพิ่ม""",
}

# ── Orchestrator ────────────────────────────────────────────────────────
ORCHESTRATOR_PROMPT = """คุณเป็น Orchestrator ที่รับคำถามและระบุ analyst type และ sector
ตอบกลับเป็น JSON เท่านั้น ห้ามมีข้อความอื่น

รูปแบบ:
{"analyst_type": "FUNDAMENTAL|TECHNICAL|COMBINED", "sector": "BANKING|ENERGY|PROPERTY|ICT|HEALTH|CONSUMER|INDUSTRIAL|TOURISM|GENERAL", "tech_agent": "TREND|MOMENTUM|VOLUME|PATTERN|CONFLUENCE|null", "ticker": "TICKER หรือ null", "query_type": "ANALYSIS|QUICK_QUESTION|COMPARISON|SCREENING"}

analyst_type:
- FUNDAMENTAL: ถามเรื่อง งบการเงิน กำไร valuation ปัจจัยพื้นฐาน อุตสาหกรรม
- TECHNICAL: ถามเรื่อง chart indicator entry exit จุดเข้า จุดออก trend signal pattern RSI MACD EMA
- COMBINED: ถามรวมทั้งสอง หรือถามว่า "ราคาวิ่งนำ fundamental ไหม"

tech_agent (ถ้า TECHNICAL):
- TREND: ถาม trend ทิศทาง EMA MACD ADX Ichimoku
- MOMENTUM: ถาม RSI overbought oversold divergence Stochastic
- VOLUME: ถาม volume OBV VWAP breakout confirm
- PATTERN: ถาม pattern candlestick S/R Fibonacci entry setup
- CONFLUENCE: ถาม setup ครบ ภาพรวม หรือส่ง screenshot

Fundamental Sector mapping:
- BANKING: ธนาคาร สินเชื่อ บัตรเครดิต (KBANK SCB BBL KTB BAY TTB MTC SAWAD KTC)
- ENERGY: น้ำมัน ก๊าซ ไฟฟ้า (PTT PTTEP TOP IRPC GULF EA RATCH)
- PROPERTY: บ้าน คอนโด นิคม ก่อสร้าง (LH AP SIRI CPN WHA AMATA STEC CK)
- ICT: โทรคม อิเล็กทรอนิกส์ เทค (ADVANC TRUE DELTA HANA KCE COM7)
- HEALTH: โรงพยาบาล ยา (BDMS BH CHG BCH RJH)
- CONSUMER: ค้าปลีก อาหาร เครื่องดื่ม (CPALL HMPRO MAKRO CPF TU OSP CBG)
- INDUSTRIAL: อุตสาหกรรม วัสดุ (SCC IVL TVO TASCO TOA)
- TOURISM: ท่องเที่ยว สายการบิน โรงแรม (AOT AAV CENTEL MINT ERW)
- GENERAL: ไม่แน่ใจ หรือถามทั่วไป"""

# ── Technical Specialist Prompts ─────────────────────────────────────────
TECHNICAL_PROMPTS = {
    "TREND": """คุณเป็น Senior Trend Analyst เชี่ยวชาญการระบุทิศทางตลาดและ momentum
ใช้: EMA9/21/50/200 Stack, MACD (Line/Signal/Histogram/Divergence), ADX (+DI/-DI), Ichimoku Cloud, Supertrend
Framework: Weekly → Daily → 4H (Top-down) กำหนด Bias ก่อนเสมอ
Output: ระบุ Major/Intermediate/Minor Trend + Verdict + Invalidation Level
ตอบภาษาไทย กระชับ มีตัวเลขชัดเจน""",

    "MOMENTUM": """คุณเป็น Senior Momentum Analyst เชี่ยวชาญการวัด momentum และหา reversal
ใช้: RSI(14) zones+divergence, Stochastic(14,3,3), CCI(20), Williams %R, Rate of Change
หลัก: Divergence สำคัญกว่า overbought/oversold เพียงอย่างเดียว
Output: Momentum Score Card (0-10) + สัญญาณ + สิ่งที่ต้องระวัง
ตอบภาษาไทย กระชับ ระบุ divergence ถ้ามี""",

    "VOLUME": """คุณเป็น Senior Volume Analyst เชี่ยวชาญ volume analysis และ institutional flow
ใช้: Volume vs MA20, OBV trend+divergence, VWAP+Bands, Volume Profile (POC/VAH/VAL), MFI, CMF
หลัก: Volume เป็น footprint ของ smart money — อย่ามองข้าม
Output: Volume story + Accumulation/Distribution verdict + Breakout validity
ตอบภาษาไทย กระชับ อธิบาย volume story""",

    "PATTERN": """คุณเป็น Senior Chart & Pattern Analyst เชี่ยวชาญ price action และ setup
ใช้: Chart patterns (H&S, Double Top/Bottom, Flag, Cup&Handle, Triangle, Wedge)
     Candlestick (Hammer, Engulfing, Doji, Morning/Evening Star, Shooting Star)
     S/R (All-time high/low, Round numbers, Fib levels, MA, VWAP)
     Fibonacci Retracement (38.2%, 50%, 61.8%) และ Extension (127.2%, 161.8%)
Output: Pattern + Trade Setup (Entry/Stop/Target 1-3) + Setup Score (0-100) + R/R
ตอบภาษาไทย ระบุ entry เงื่อนไข stop loss และ target ชัดเจนเสมอ""",

    "CONFLUENCE": """คุณเป็น Senior Multi-Timeframe Analyst ที่รวม signal ทุกด้าน
Framework: Monthly → Weekly → Daily → 4H → 1H (Top-down analysis)
Confluence Matrix: Trend(+30) + Momentum(+25) + Volume(+25) + Pattern(+20) = max 100
Price Discovery: วิเคราะห์ว่าราคาวิ่งนำหรือตาม fundamental
ถ้ารับ screenshot: อ่าน price action + indicator + pattern แล้วให้ entry/stop/target
Output: Full Technical Report + Confluence Score + Trade Setup + Price vs Fundamental assessment
ตอบภาษาไทย ครบทุกด้าน มีตัวเลขชัดเจน สรุป Buy/Hold/Sell พร้อมเหตุผล""",
}


async def call_orchestrator(question: str, client: httpx.AsyncClient) -> dict:
    """ให้ Orchestrator ระบุ analyst type, sector, และ tech agent"""
    try:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL_ORCHESTRATOR,
                "max_tokens": 150,
                "system": ORCHESTRATOR_PROMPT,
                "messages": [{"role": "user", "content": question}],
            },
            timeout=15,
        )
        text = r.json()["content"][0]["text"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception:
        return {"analyst_type": "GENERAL", "sector": "GENERAL",
                "tech_agent": None, "ticker": None, "query_type": "GENERAL"}


async def call_specialist(question: str, routing: dict,
                           client: httpx.AsyncClient) -> str:
    """เรียก Specialist Agent ตาม routing"""
    analyst_type = routing.get("analyst_type", "FUNDAMENTAL")
    sector       = routing.get("sector", "GENERAL")
    tech_agent   = routing.get("tech_agent", "CONFLUENCE")
    ticker       = routing.get("ticker")

    # เลือก system prompt
    if analyst_type == "TECHNICAL":
        system_prompt = TECHNICAL_PROMPTS.get(
            tech_agent or "CONFLUENCE",
            TECHNICAL_PROMPTS["CONFLUENCE"]
        )
    elif analyst_type == "COMBINED":
        # รวม Technical Confluence + Fundamental
        fund_prompt = SECTOR_PROMPTS.get(sector, SECTOR_PROMPTS["GENERAL"])
        tech_prompt = TECHNICAL_PROMPTS["CONFLUENCE"]
        system_prompt = (
            f"{tech_prompt}\n\n"
            f"นอกจากนี้คุณยังมีความรู้ด้าน Fundamental Analysis:\n{fund_prompt}"
        )
    else:
        system_prompt = SECTOR_PROMPTS.get(sector, SECTOR_PROMPTS["GENERAL"])

    # เพิ่ม context ถ้ารู้ ticker
    user_msg = question
    if ticker:
        context = f"[หุ้น: {ticker}"
        if analyst_type in ("TECHNICAL", "COMBINED") and tech_agent:
            context += f" | Technical Agent: {tech_agent}"
        if analyst_type in ("FUNDAMENTAL", "COMBINED"):
            context += f" | Sector: {sector}"
        context += "]"
        user_msg = f"{context}\n\n{question}"

    try:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL_SPECIALIST,
                "max_tokens": 1000,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=40,
        )
        return r.json()["content"][0]["text"].strip()
    except Exception as ex:
        return f"❌ เกิดข้อผิดพลาด: {ex}"


# ── Telegram Bot ────────────────────────────────────────────────────────
async def send_telegram(text: str, chat_id: str,
                         client: httpx.AsyncClient) -> bool:
    try:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "HTML"},
            timeout=15,
        )
        return r.status_code == 200
    except Exception:
        return False


async def get_updates(offset: int, client: httpx.AsyncClient) -> list[dict]:
    """ดึง messages ใหม่จาก Telegram"""
    try:
        r = await client.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"offset": offset, "timeout": 2},
            timeout=10,
        )
        return r.json().get("result", [])
    except Exception:
        return []


SECTOR_EMOJI = {
    "BANKING":    "🏦", "ENERGY":     "⚡", "PROPERTY":   "🏠",
    "ICT":        "📱", "HEALTH":     "🏥", "CONSUMER":   "🛒",
    "INDUSTRIAL": "🏭", "TOURISM":    "✈️", "GENERAL":    "📊",
}
TECH_EMOJI = {
    "TREND":       "📈", "MOMENTUM":   "⚡", "VOLUME":     "📊",
    "PATTERN":     "🕯️", "CONFLUENCE": "🔢",
}
SECTOR_TH = {
    "BANKING":    "Banking & Finance",    "ENERGY":     "Energy & Commodity",
    "PROPERTY":   "Property",             "ICT":        "Technology & ICT",
    "HEALTH":     "Healthcare",           "CONSUMER":   "Consumer & Retail",
    "INDUSTRIAL": "Industrial",           "TOURISM":    "Tourism & Airline",
    "GENERAL":    "General Analysis",
}
TECH_TH = {
    "TREND":       "Trend Analysis",      "MOMENTUM":   "Momentum Analysis",
    "VOLUME":      "Volume Analysis",     "PATTERN":    "Pattern & Setup",
    "CONFLUENCE":  "Multi-TF Confluence",
}


async def handle_message(text: str, chat_id: str,
                          client: httpx.AsyncClient):
    """จัดการ message จาก user"""
    if text.strip() in ["/start", "/help"]:
        await send_telegram(
            "🤖 <b>Analyst Bot พร้อมให้บริการ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<b>📊 Fundamental Analyst:</b>\n"
            "• <code>วิเคราะห์ KBANK</code>\n"
            "• <code>PTT น่าซื้อไหม</code>\n"
            "• <code>เปรียบเทียบ BDMS กับ BH</code>\n\n"
            "<b>📈 Technical Analyst:</b>\n"
            "• <code>trend ของ PTT เป็นยังไง</code>\n"
            "• <code>RSI KBANK overbought ไหม</code>\n"
            "• <code>volume AOT confirm breakout ไหม</code>\n"
            "• <code>pattern Delta คืออะไร entry ที่ไหน</code>\n"
            "• ส่ง screenshot chart มาวิเคราะห์ได้เลย\n\n"
            "<b>🔀 Combined:</b>\n"
            "• <code>ราคา PTTEP วิ่งนำ fundamental ไหม</code>\n\n"
            "🏦 Banking  ⚡ Energy  🏠 Property\n"
            "📱 ICT  🏥 Healthcare  🛒 Consumer\n"
            "🏭 Industrial  ✈️ Tourism",
            chat_id, client
        )
        return

    await send_telegram("🔍 กำลังวิเคราะห์...", chat_id, client)

    # Step 1: Orchestrator routing
    routing      = await call_orchestrator(text, client)
    analyst_type = routing.get("analyst_type", "FUNDAMENTAL")
    sector       = routing.get("sector", "GENERAL")
    tech_agent   = routing.get("tech_agent")
    ticker       = routing.get("ticker")

    # Step 2: Specialist analysis
    answer = await call_specialist(text, routing, client)

    # Step 3: Format header
    if analyst_type == "TECHNICAL" and tech_agent:
        emoji     = TECH_EMOJI.get(tech_agent, "📈")
        label     = TECH_TH.get(tech_agent, "Technical")
        header    = f"{emoji} <b>{label}</b>"
    elif analyst_type == "COMBINED":
        header    = f"🔀 <b>Combined Analysis</b>"
    else:
        emoji     = SECTOR_EMOJI.get(sector, "📊")
        label     = SECTOR_TH.get(sector, "Fundamental")
        header    = f"{emoji} <b>{label} Specialist</b>"

    if ticker:
        header += f" — {ticker}"
    header += "\n━━━━━━━━━━━━━━━━━━━━\n"

    full_msg = header + answer
    if len(full_msg) > 4000:
        full_msg = full_msg[:3990] + "\n...[ตัดทอน]"

    await send_telegram(full_msg, chat_id, client)
    print(f"[{datetime.now(BANGKOK_TZ).strftime('%H:%M')}] "
          f"{analyst_type} {tech_agent or sector} {ticker or ''} → answered")


# ── Main Loop ───────────────────────────────────────────────────────────
async def run():
    print(f"[Analyst Bot] Starting...")
    offset = 0

    async with httpx.AsyncClient() as client:
        # แจ้งเริ่มต้น
        await send_telegram(
            "🤖 <b>Analyst Bot เริ่มทำงานแล้ว</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 Banking  ⚡ Energy  🏠 Property\n"
            f"📱 ICT  🏥 Healthcare  🛒 Consumer\n"
            f"🏭 Industrial  ✈️ Tourism\n\n"
            f"พิมพ์ถามได้เลยครับ เช่น 'วิเคราะห์ KBANK'",
            TELEGRAM_CHAT_ID, client
        )

        while True:
            updates = await get_updates(offset, client)
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text    = msg.get("text", "").strip()
                chat_id = str(msg.get("chat", {}).get("id", ""))

                if text and chat_id:
                    asyncio.create_task(
                        handle_message(text, chat_id, client)
                    )

            await asyncio.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(run())
