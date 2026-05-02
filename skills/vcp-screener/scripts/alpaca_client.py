#!/usr/bin/env python3
"""
Alpaca Data API Client for VCP Screener

Drop-in replacement for FMPClient using Alpaca's market data API.
Implements the same interface: get_sp500_constituents, get_batch_quotes,
get_historical_prices, get_api_stats.

Authentication: ALPACA_API_KEY + ALPACA_API_SECRET environment variables
(also accepts APCA_API_KEY_ID + APCA_API_SECRET_KEY for legacy naming).
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import requests
except ImportError:
    print("ERROR: requests library not found. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# S&P 500 universe — symbols + sector (sector used for report display only)
# ---------------------------------------------------------------------------

_SP500 = [
    # Information Technology
    ("AAPL", "Apple Inc", "Information Technology"),
    ("MSFT", "Microsoft Corp", "Information Technology"),
    ("NVDA", "NVIDIA Corp", "Information Technology"),
    ("AVGO", "Broadcom Inc", "Information Technology"),
    ("ORCL", "Oracle Corp", "Information Technology"),
    ("CRM", "Salesforce Inc", "Information Technology"),
    ("ACN", "Accenture PLC", "Information Technology"),
    ("AMD", "Advanced Micro Devices", "Information Technology"),
    ("CSCO", "Cisco Systems", "Information Technology"),
    ("IBM", "IBM Corp", "Information Technology"),
    ("INTU", "Intuit Inc", "Information Technology"),
    ("NOW", "ServiceNow Inc", "Information Technology"),
    ("TXN", "Texas Instruments", "Information Technology"),
    ("QCOM", "Qualcomm Inc", "Information Technology"),
    ("AMAT", "Applied Materials", "Information Technology"),
    ("MU", "Micron Technology", "Information Technology"),
    ("LRCX", "Lam Research", "Information Technology"),
    ("KLAC", "KLA Corp", "Information Technology"),
    ("ADI", "Analog Devices", "Information Technology"),
    ("MRVL", "Marvell Technology", "Information Technology"),
    ("ADBE", "Adobe Inc", "Information Technology"),
    ("PANW", "Palo Alto Networks", "Information Technology"),
    ("CDNS", "Cadence Design Systems", "Information Technology"),
    ("SNPS", "Synopsys Inc", "Information Technology"),
    ("FTNT", "Fortinet Inc", "Information Technology"),
    ("HPQ", "HP Inc", "Information Technology"),
    ("HPE", "Hewlett Packard Enterprise", "Information Technology"),
    ("WDC", "Western Digital", "Information Technology"),
    ("STX", "Seagate Technology", "Information Technology"),
    ("GLW", "Corning Inc", "Information Technology"),
    ("KEYS", "Keysight Technologies", "Information Technology"),
    ("TEL", "TE Connectivity", "Information Technology"),
    ("ZBRA", "Zebra Technologies", "Information Technology"),
    ("JNPR", "Juniper Networks", "Information Technology"),
    ("NTAP", "NetApp Inc", "Information Technology"),
    ("CTSH", "Cognizant Technology", "Information Technology"),
    ("AKAM", "Akamai Technologies", "Information Technology"),
    ("EPAM", "EPAM Systems", "Information Technology"),
    ("PTC", "PTC Inc", "Information Technology"),
    ("GEN", "Gen Digital", "Information Technology"),
    ("TDY", "Teledyne Technologies", "Information Technology"),
    ("ANSS", "ANSYS Inc", "Information Technology"),
    ("MPWR", "Monolithic Power Systems", "Information Technology"),
    ("TER", "Teradyne Inc", "Information Technology"),
    ("ENPH", "Enphase Energy", "Information Technology"),
    ("ON", "ON Semiconductor", "Information Technology"),
    ("SWKS", "Skyworks Solutions", "Information Technology"),
    ("QRVO", "Qorvo Inc", "Information Technology"),
    ("IT", "Gartner Inc", "Information Technology"),
    ("CDW", "CDW Corp", "Information Technology"),

    # Communication Services
    ("GOOGL", "Alphabet Inc Class A", "Communication Services"),
    ("GOOG", "Alphabet Inc Class C", "Communication Services"),
    ("META", "Meta Platforms", "Communication Services"),
    ("NFLX", "Netflix Inc", "Communication Services"),
    ("DIS", "Walt Disney Co", "Communication Services"),
    ("CMCSA", "Comcast Corp", "Communication Services"),
    ("T", "AT&T Inc", "Communication Services"),
    ("VZ", "Verizon Communications", "Communication Services"),
    ("TMUS", "T-Mobile US", "Communication Services"),
    ("CHTR", "Charter Communications", "Communication Services"),
    ("PARA", "Paramount Global", "Communication Services"),
    ("WBD", "Warner Bros Discovery", "Communication Services"),
    ("OMC", "Omnicom Group", "Communication Services"),
    ("IPG", "Interpublic Group", "Communication Services"),
    ("FOXA", "Fox Corp Class A", "Communication Services"),
    ("EA", "Electronic Arts", "Communication Services"),
    ("TTWO", "Take-Two Interactive", "Communication Services"),
    ("MTCH", "Match Group", "Communication Services"),
    ("LYV", "Live Nation Entertainment", "Communication Services"),
    ("ZM", "Zoom Video", "Communication Services"),

    # Consumer Discretionary
    ("AMZN", "Amazon.com Inc", "Consumer Discretionary"),
    ("TSLA", "Tesla Inc", "Consumer Discretionary"),
    ("HD", "Home Depot", "Consumer Discretionary"),
    ("MCD", "McDonald's Corp", "Consumer Discretionary"),
    ("NKE", "Nike Inc", "Consumer Discretionary"),
    ("LOW", "Lowe's Companies", "Consumer Discretionary"),
    ("SBUX", "Starbucks Corp", "Consumer Discretionary"),
    ("TJX", "TJX Companies", "Consumer Discretionary"),
    ("BKNG", "Booking Holdings", "Consumer Discretionary"),
    ("CMG", "Chipotle Mexican Grill", "Consumer Discretionary"),
    ("ABNB", "Airbnb Inc", "Consumer Discretionary"),
    ("YUM", "Yum! Brands", "Consumer Discretionary"),
    ("DPZ", "Domino's Pizza", "Consumer Discretionary"),
    ("ROST", "Ross Stores", "Consumer Discretionary"),
    ("ORLY", "O'Reilly Automotive", "Consumer Discretionary"),
    ("AZO", "AutoZone Inc", "Consumer Discretionary"),
    ("GPC", "Genuine Parts", "Consumer Discretionary"),
    ("BBY", "Best Buy", "Consumer Discretionary"),
    ("TGT", "Target Corp", "Consumer Discretionary"),
    ("DG", "Dollar General", "Consumer Discretionary"),
    ("DLTR", "Dollar Tree", "Consumer Discretionary"),
    ("LVS", "Las Vegas Sands", "Consumer Discretionary"),
    ("MGM", "MGM Resorts", "Consumer Discretionary"),
    ("WYNN", "Wynn Resorts", "Consumer Discretionary"),
    ("MAR", "Marriott International", "Consumer Discretionary"),
    ("HLT", "Hilton Worldwide", "Consumer Discretionary"),
    ("HAS", "Hasbro Inc", "Consumer Discretionary"),
    ("PHM", "PulteGroup Inc", "Consumer Discretionary"),
    ("DHI", "D.R. Horton", "Consumer Discretionary"),
    ("LEN", "Lennar Corp", "Consumer Discretionary"),
    ("NVR", "NVR Inc", "Consumer Discretionary"),
    ("TOL", "Toll Brothers", "Consumer Discretionary"),
    ("F", "Ford Motor", "Consumer Discretionary"),
    ("GM", "General Motors", "Consumer Discretionary"),
    ("APTV", "Aptiv PLC", "Consumer Discretionary"),
    ("BWA", "BorgWarner Inc", "Consumer Discretionary"),
    ("RL", "Ralph Lauren", "Consumer Discretionary"),
    ("TPR", "Tapestry Inc", "Consumer Discretionary"),
    ("PVH", "PVH Corp", "Consumer Discretionary"),
    ("VFC", "VF Corp", "Consumer Discretionary"),
    ("ETSY", "Etsy Inc", "Consumer Discretionary"),

    # Consumer Staples
    ("WMT", "Walmart Inc", "Consumer Staples"),
    ("PG", "Procter & Gamble", "Consumer Staples"),
    ("KO", "Coca-Cola Co", "Consumer Staples"),
    ("PEP", "PepsiCo Inc", "Consumer Staples"),
    ("COST", "Costco Wholesale", "Consumer Staples"),
    ("PM", "Philip Morris", "Consumer Staples"),
    ("MO", "Altria Group", "Consumer Staples"),
    ("CL", "Colgate-Palmolive", "Consumer Staples"),
    ("KMB", "Kimberly-Clark", "Consumer Staples"),
    ("EL", "Estee Lauder", "Consumer Staples"),
    ("CHD", "Church & Dwight", "Consumer Staples"),
    ("CLX", "Clorox Co", "Consumer Staples"),
    ("HRL", "Hormel Foods", "Consumer Staples"),
    ("SJM", "JM Smucker", "Consumer Staples"),
    ("GIS", "General Mills", "Consumer Staples"),
    ("CPB", "Campbell Soup", "Consumer Staples"),
    ("K", "Kellanova", "Consumer Staples"),
    ("MKC", "McCormick & Co", "Consumer Staples"),
    ("HSY", "Hershey Co", "Consumer Staples"),
    ("MDLZ", "Mondelez International", "Consumer Staples"),
    ("KHC", "Kraft Heinz", "Consumer Staples"),
    ("TSN", "Tyson Foods", "Consumer Staples"),
    ("CAG", "Conagra Brands", "Consumer Staples"),
    ("KR", "Kroger Co", "Consumer Staples"),
    ("SFM", "Sprouts Farmers Market", "Consumer Staples"),
    ("KVUE", "Kenvue Inc", "Consumer Staples"),
    ("BG", "Bunge Global", "Consumer Staples"),
    ("ADM", "Archer-Daniels-Midland", "Consumer Staples"),
    ("TAP", "Molson Coors Beverage", "Consumer Staples"),
    ("STZ", "Constellation Brands", "Consumer Staples"),

    # Health Care
    ("LLY", "Eli Lilly", "Health Care"),
    ("UNH", "UnitedHealth Group", "Health Care"),
    ("JNJ", "Johnson & Johnson", "Health Care"),
    ("ABT", "Abbott Laboratories", "Health Care"),
    ("MRK", "Merck & Co", "Health Care"),
    ("TMO", "Thermo Fisher Scientific", "Health Care"),
    ("DHR", "Danaher Corp", "Health Care"),
    ("ABBV", "AbbVie Inc", "Health Care"),
    ("BMY", "Bristol-Myers Squibb", "Health Care"),
    ("PFE", "Pfizer Inc", "Health Care"),
    ("AMGN", "Amgen Inc", "Health Care"),
    ("GILD", "Gilead Sciences", "Health Care"),
    ("REGN", "Regeneron Pharmaceuticals", "Health Care"),
    ("VRTX", "Vertex Pharmaceuticals", "Health Care"),
    ("BIIB", "Biogen Inc", "Health Care"),
    ("ILMN", "Illumina Inc", "Health Care"),
    ("MRNA", "Moderna Inc", "Health Care"),
    ("ISRG", "Intuitive Surgical", "Health Care"),
    ("BSX", "Boston Scientific", "Health Care"),
    ("MDT", "Medtronic PLC", "Health Care"),
    ("SYK", "Stryker Corp", "Health Care"),
    ("EW", "Edwards Lifesciences", "Health Care"),
    ("ZBH", "Zimmer Biomet", "Health Care"),
    ("BDX", "Becton Dickinson", "Health Care"),
    ("BAX", "Baxter International", "Health Care"),
    ("IQV", "IQVIA Holdings", "Health Care"),
    ("A", "Agilent Technologies", "Health Care"),
    ("IDXX", "IDEXX Laboratories", "Health Care"),
    ("DXCM", "DexCom Inc", "Health Care"),
    ("HOLX", "Hologic Inc", "Health Care"),
    ("CAH", "Cardinal Health", "Health Care"),
    ("MCK", "McKesson Corp", "Health Care"),
    ("CNC", "Centene Corp", "Health Care"),
    ("ELV", "Elevance Health", "Health Care"),
    ("HUM", "Humana Inc", "Health Care"),
    ("CI", "Cigna Group", "Health Care"),
    ("CVS", "CVS Health", "Health Care"),
    ("MOH", "Molina Healthcare", "Health Care"),
    ("HCA", "HCA Healthcare", "Health Care"),
    ("THC", "Tenet Healthcare", "Health Care"),
    ("DVA", "DaVita Inc", "Health Care"),
    ("ZTS", "Zoetis Inc", "Health Care"),
    ("ALGN", "Align Technology", "Health Care"),
    ("TECH", "Bio-Techne Corp", "Health Care"),
    ("MTD", "Mettler-Toledo", "Health Care"),
    ("RMD", "ResMed Inc", "Health Care"),
    ("PODD", "Insulet Corp", "Health Care"),
    ("GEHC", "GE HealthCare", "Health Care"),
    ("SOLV", "Solventum Corp", "Health Care"),

    # Financials
    ("BRK/B", "Berkshire Hathaway", "Financials"),
    ("JPM", "JPMorgan Chase", "Financials"),
    ("V", "Visa Inc", "Financials"),
    ("MA", "Mastercard Inc", "Financials"),
    ("BAC", "Bank of America", "Financials"),
    ("WFC", "Wells Fargo", "Financials"),
    ("GS", "Goldman Sachs", "Financials"),
    ("MS", "Morgan Stanley", "Financials"),
    ("BLK", "BlackRock Inc", "Financials"),
    ("AXP", "American Express", "Financials"),
    ("SPGI", "S&P Global", "Financials"),
    ("MCO", "Moody's Corp", "Financials"),
    ("CME", "CME Group", "Financials"),
    ("ICE", "Intercontinental Exchange", "Financials"),
    ("CBOE", "Cboe Global Markets", "Financials"),
    ("MSCI", "MSCI Inc", "Financials"),
    ("FI", "Fiserv Inc", "Financials"),
    ("FIS", "Fidelity National Info", "Financials"),
    ("PYPL", "PayPal Holdings", "Financials"),
    ("COF", "Capital One Financial", "Financials"),
    ("DFS", "Discover Financial", "Financials"),
    ("SYF", "Synchrony Financial", "Financials"),
    ("USB", "US Bancorp", "Financials"),
    ("TFC", "Truist Financial", "Financials"),
    ("PNC", "PNC Financial Services", "Financials"),
    ("FITB", "Fifth Third Bancorp", "Financials"),
    ("KEY", "KeyCorp", "Financials"),
    ("RF", "Regions Financial", "Financials"),
    ("HBAN", "Huntington Bancshares", "Financials"),
    ("CFG", "Citizens Financial", "Financials"),
    ("MTB", "M&T Bank", "Financials"),
    ("CMA", "Comerica Inc", "Financials"),
    ("ZION", "Zions Bancorporation", "Financials"),
    ("C", "Citigroup Inc", "Financials"),
    ("AIG", "American International Group", "Financials"),
    ("MET", "MetLife Inc", "Financials"),
    ("PRU", "Prudential Financial", "Financials"),
    ("LNC", "Lincoln National", "Financials"),
    ("AFL", "Aflac Inc", "Financials"),
    ("HIG", "Hartford Financial", "Financials"),
    ("ALL", "Allstate Corp", "Financials"),
    ("PGR", "Progressive Corp", "Financials"),
    ("TRV", "Travelers Companies", "Financials"),
    ("CB", "Chubb Ltd", "Financials"),
    ("MMC", "Marsh & McLennan", "Financials"),
    ("AON", "Aon PLC", "Financials"),
    ("WTW", "Willis Towers Watson", "Financials"),
    ("RE", "Everest Group", "Financials"),
    ("GL", "Globe Life Inc", "Financials"),
    ("CINF", "Cincinnati Financial", "Financials"),
    ("RJF", "Raymond James Financial", "Financials"),
    ("AMTD", "Ameritrade (TD)", "Financials"),
    ("SCHW", "Charles Schwab", "Financials"),
    ("STT", "State Street Corp", "Financials"),
    ("NTRS", "Northern Trust", "Financials"),
    ("BK", "Bank of New York Mellon", "Financials"),
    ("IVZ", "Invesco Ltd", "Financials"),
    ("BEN", "Franklin Resources", "Financials"),
    ("TROW", "T. Rowe Price", "Financials"),
    ("AMP", "Ameriprise Financial", "Financials"),
    ("NDAQ", "Nasdaq Inc", "Financials"),
    ("MKTX", "MarketAxess Holdings", "Financials"),

    # Industrials
    ("GE", "GE Aerospace", "Industrials"),
    ("RTX", "RTX Corp", "Industrials"),
    ("CAT", "Caterpillar Inc", "Industrials"),
    ("HON", "Honeywell International", "Industrials"),
    ("UPS", "United Parcel Service", "Industrials"),
    ("BA", "Boeing Co", "Industrials"),
    ("LMT", "Lockheed Martin", "Industrials"),
    ("NOC", "Northrop Grumman", "Industrials"),
    ("GD", "General Dynamics", "Industrials"),
    ("LHX", "L3Harris Technologies", "Industrials"),
    ("TDG", "TransDigm Group", "Industrials"),
    ("HEI", "HEICO Corp", "Industrials"),
    ("HII", "Huntington Ingalls", "Industrials"),
    ("AXON", "Axon Enterprise", "Industrials"),
    ("DE", "Deere & Co", "Industrials"),
    ("PCAR", "PACCAR Inc", "Industrials"),
    ("CMI", "Cummins Inc", "Industrials"),
    ("EMR", "Emerson Electric", "Industrials"),
    ("ETN", "Eaton Corp", "Industrials"),
    ("PH", "Parker Hannifin", "Industrials"),
    ("ITW", "Illinois Tool Works", "Industrials"),
    ("MMM", "3M Company", "Industrials"),
    ("DOV", "Dover Corp", "Industrials"),
    ("XYL", "Xylem Inc", "Industrials"),
    ("IR", "Ingersoll Rand", "Industrials"),
    ("CARR", "Carrier Global", "Industrials"),
    ("OTIS", "Otis Worldwide", "Industrials"),
    ("TT", "Trane Technologies", "Industrials"),
    ("JCI", "Johnson Controls", "Industrials"),
    ("CTAS", "Cintas Corp", "Industrials"),
    ("RSG", "Republic Services", "Industrials"),
    ("WM", "Waste Management", "Industrials"),
    ("VRSK", "Verisk Analytics", "Industrials"),
    ("BR", "Broadridge Financial", "Industrials"),
    ("FAST", "Fastenal Co", "Industrials"),
    ("GWW", "W.W. Grainger", "Industrials"),
    ("SWK", "Stanley Black & Decker", "Industrials"),
    ("FTV", "Fortive Corp", "Industrials"),
    ("ROK", "Rockwell Automation", "Industrials"),
    ("AME", "AMETEK Inc", "Industrials"),
    ("ROP", "Roper Technologies", "Industrials"),
    ("LDOS", "Leidos Holdings", "Industrials"),
    ("SAIC", "SAIC Inc", "Industrials"),
    ("MAN", "ManpowerGroup", "Industrials"),
    ("ADP", "Automatic Data Processing", "Industrials"),
    ("PAYX", "Paychex Inc", "Industrials"),
    ("EFX", "Equifax Inc", "Industrials"),
    ("TRI", "Thomson Reuters", "Industrials"),
    ("EXPD", "Expeditors International", "Industrials"),
    ("FDX", "FedEx Corp", "Industrials"),
    ("DAL", "Delta Air Lines", "Industrials"),
    ("UAL", "United Airlines", "Industrials"),
    ("AAL", "American Airlines", "Industrials"),
    ("LUV", "Southwest Airlines", "Industrials"),
    ("ALK", "Alaska Air Group", "Industrials"),
    ("JBLU", "JetBlue Airways", "Industrials"),
    ("CSX", "CSX Corp", "Industrials"),
    ("NSC", "Norfolk Southern", "Industrials"),
    ("UNP", "Union Pacific", "Industrials"),
    ("CP", "Canadian Pacific Kansas City", "Industrials"),
    ("CNI", "Canadian National Railway", "Industrials"),

    # Energy
    ("XOM", "Exxon Mobil", "Energy"),
    ("CVX", "Chevron Corp", "Energy"),
    ("COP", "ConocoPhillips", "Energy"),
    ("EOG", "EOG Resources", "Energy"),
    ("SLB", "SLB (Schlumberger)", "Energy"),
    ("MPC", "Marathon Petroleum", "Energy"),
    ("PSX", "Phillips 66", "Energy"),
    ("VLO", "Valero Energy", "Energy"),
    ("PXD", "Pioneer Natural Resources", "Energy"),
    ("DVN", "Devon Energy", "Energy"),
    ("FANG", "Diamondback Energy", "Energy"),
    ("HAL", "Halliburton Co", "Energy"),
    ("BKR", "Baker Hughes", "Energy"),
    ("OXY", "Occidental Petroleum", "Energy"),
    ("HES", "Hess Corp", "Energy"),
    ("APA", "APA Corp", "Energy"),
    ("MRO", "Marathon Oil", "Energy"),
    ("OKE", "ONEOK Inc", "Energy"),
    ("WMB", "Williams Companies", "Energy"),
    ("KMI", "Kinder Morgan", "Energy"),
    ("ET", "Energy Transfer", "Energy"),
    ("LNG", "Cheniere Energy", "Energy"),
    ("EQT", "EQT Corp", "Energy"),
    ("CTRA", "Coterra Energy", "Energy"),
    ("RRC", "Range Resources", "Energy"),
    ("AR", "Antero Resources", "Energy"),
    ("PR", "Permian Resources", "Energy"),

    # Materials
    ("LIN", "Linde PLC", "Materials"),
    ("APD", "Air Products & Chemicals", "Materials"),
    ("SHW", "Sherwin-Williams", "Materials"),
    ("ECL", "Ecolab Inc", "Materials"),
    ("NEM", "Newmont Corp", "Materials"),
    ("FCX", "Freeport-McMoRan", "Materials"),
    ("NUE", "Nucor Corp", "Materials"),
    ("STLD", "Steel Dynamics", "Materials"),
    ("RS", "Reliance Steel", "Materials"),
    ("X", "United States Steel", "Materials"),
    ("CF", "CF Industries", "Materials"),
    ("MOS", "Mosaic Co", "Materials"),
    ("ALB", "Albemarle Corp", "Materials"),
    ("PPG", "PPG Industries", "Materials"),
    ("RPM", "RPM International", "Materials"),
    ("CE", "Celanese Corp", "Materials"),
    ("HUN", "Huntsman Corp", "Materials"),
    ("EMN", "Eastman Chemical", "Materials"),
    ("FMC", "FMC Corp", "Materials"),
    ("IP", "International Paper", "Materials"),
    ("PKG", "Packaging Corp of America", "Materials"),
    ("WRK", "WestRock Co", "Materials"),
    ("AVY", "Avery Dennison", "Materials"),
    ("SEE", "Sealed Air Corp", "Materials"),
    ("IFF", "International Flavors", "Materials"),
    ("PPL", "PPL Corp", "Materials"),

    # Real Estate
    ("AMT", "American Tower", "Real Estate"),
    ("PLD", "Prologis Inc", "Real Estate"),
    ("EQIX", "Equinix Inc", "Real Estate"),
    ("CCI", "Crown Castle", "Real Estate"),
    ("SBAC", "SBA Communications", "Real Estate"),
    ("DLR", "Digital Realty Trust", "Real Estate"),
    ("SPG", "Simon Property Group", "Real Estate"),
    ("O", "Realty Income", "Real Estate"),
    ("WELL", "Welltower Inc", "Real Estate"),
    ("VICI", "VICI Properties", "Real Estate"),
    ("PSA", "Public Storage", "Real Estate"),
    ("EXR", "Extra Space Storage", "Real Estate"),
    ("AVB", "AvalonBay Communities", "Real Estate"),
    ("EQR", "Equity Residential", "Real Estate"),
    ("MAA", "Mid-America Apartment", "Real Estate"),
    ("UDR", "UDR Inc", "Real Estate"),
    ("CPT", "Camden Property Trust", "Real Estate"),
    ("NNN", "NNN REIT", "Real Estate"),
    ("REG", "Regency Centers", "Real Estate"),
    ("FRT", "Federal Realty Investment", "Real Estate"),
    ("KIM", "Kimco Realty", "Real Estate"),
    ("HST", "Host Hotels & Resorts", "Real Estate"),
    ("IRM", "Iron Mountain", "Real Estate"),
    ("WY", "Weyerhaeuser Co", "Real Estate"),
    ("ARE", "Alexandria Real Estate", "Real Estate"),
    ("BXP", "BXP Inc", "Real Estate"),
    ("SLG", "SL Green Realty", "Real Estate"),
    ("CBRE", "CBRE Group", "Real Estate"),
    ("VTR", "Ventas Inc", "Real Estate"),

    # Utilities
    ("NEE", "NextEra Energy", "Utilities"),
    ("SO", "Southern Company", "Utilities"),
    ("DUK", "Duke Energy", "Utilities"),
    ("D", "Dominion Energy", "Utilities"),
    ("EXC", "Exelon Corp", "Utilities"),
    ("SRE", "Sempra Energy", "Utilities"),
    ("AEP", "American Electric Power", "Utilities"),
    ("XEL", "Xcel Energy", "Utilities"),
    ("PCG", "PG&E Corp", "Utilities"),
    ("ED", "Consolidated Edison", "Utilities"),
    ("ETR", "Entergy Corp", "Utilities"),
    ("PEG", "PSEG Inc", "Utilities"),
    ("FE", "FirstEnergy Corp", "Utilities"),
    ("EIX", "Edison International", "Utilities"),
    ("WEC", "WEC Energy Group", "Utilities"),
    ("DTE", "DTE Energy", "Utilities"),
    ("ES", "Eversource Energy", "Utilities"),
    ("CNP", "CenterPoint Energy", "Utilities"),
    ("NI", "NiSource Inc", "Utilities"),
    ("LNT", "Alliant Energy", "Utilities"),
    ("ATO", "Atmos Energy", "Utilities"),
    ("AWK", "American Water Works", "Utilities"),
    ("WTRG", "Essential Utilities", "Utilities"),
    ("CMS", "CMS Energy", "Utilities"),
    ("AEE", "Ameren Corp", "Utilities"),
    ("EVRG", "Evergy Inc", "Utilities"),
    ("OGE", "OGE Energy", "Utilities"),
    ("NRG", "NRG Energy", "Utilities"),
    ("CEG", "Constellation Energy", "Utilities"),
    ("VST", "Vistra Corp", "Utilities"),
    ("AES", "AES Corp", "Utilities"),
    ("BEP", "Brookfield Renewable", "Utilities"),
]


class AlpacaClient:
    """Alpaca Data API client — drop-in replacement for FMPClient."""

    DATA_BASE_URL = "https://data.alpaca.markets/v2"
    RATE_LIMIT_DELAY = 0.05  # Alpaca allows 200 req/min on free tier

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = (
            api_key
            or os.getenv("ALPACA_API_KEY")
            or os.getenv("APCA_API_KEY_ID")
        )
        self.api_secret = (
            api_secret
            or os.getenv("ALPACA_API_SECRET")
            or os.getenv("APCA_API_SECRET_KEY")
        )
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Alpaca API key and secret required. "
                "Set ALPACA_API_KEY and ALPACA_API_SECRET environment variables."
            )

        self.session = requests.Session()
        self.session.headers.update({
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        })
        self.cache: dict = {}
        self.last_call_time: float = 0.0
        self.api_calls_made: int = 0
        self._use_iex: bool = False  # auto-set on first SIP 403

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """Rate-limited GET with basic error handling and IEX feed auto-detection."""
        if params is None:
            params = {}

        # Inject feed=iex once detected (free-tier accounts require it for recent data)
        if self._use_iex and "feed" not in params:
            params = {**params, "feed": "iex"}

        elapsed = time.time() - self.last_call_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)

        try:
            resp = self.session.get(url, params=params, timeout=30)
            self.last_call_time = time.time()
            self.api_calls_made += 1

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 403 and "subscription does not permit" in resp.text:
                if not self._use_iex:
                    print("  INFO: Free-tier account detected — switching to IEX feed", flush=True)
                    self._use_iex = True
                    return self._get(url, params)
                return None
            elif resp.status_code == 429:
                print("  WARNING: Alpaca rate limit hit — waiting 60s...", file=sys.stderr)
                time.sleep(60)
                return self._get(url, params)
            else:
                print(
                    f"  WARNING: Alpaca API {resp.status_code} for {url}: {resp.text[:200]}",
                    file=sys.stderr,
                )
                return None
        except requests.exceptions.RequestException as e:
            print(f"  ERROR: Request failed: {e}", file=sys.stderr)
            return None

    @staticmethod
    def _convert_bars(alpaca_bars: list[dict]) -> list[dict]:
        """Convert Alpaca bar list to FMP historical format (most-recent-first)."""
        result = []
        for bar in alpaca_bars:
            t = bar.get("t", "")
            date = t[:10] if t else ""
            result.append({
                "date": date,
                "open": bar.get("o", 0.0),
                "high": bar.get("h", 0.0),
                "low": bar.get("l", 0.0),
                "close": bar.get("c", 0.0),
                "volume": bar.get("v", 0),
            })
        result.sort(key=lambda x: x["date"], reverse=True)
        return result

    @staticmethod
    def _bars_to_quote(symbol: str, historical: list[dict]) -> dict:
        """Derive a quote-like dict from historical bars."""
        if not historical:
            return {}
        latest = historical[0]
        year_bars = historical[:252]
        year_high = max(b["high"] for b in year_bars) if year_bars else 0.0
        year_low = min(b["low"] for b in year_bars) if year_bars else 0.0
        n = min(50, len(historical))
        avg_volume = int(sum(b["volume"] for b in historical[:n]) / n) if n else 0
        return {
            "symbol": symbol,
            "price": latest["close"],
            "yearHigh": year_high,
            "yearLow": year_low,
            "avgVolume": avg_volume,
            "marketCap": 0,
        }

    def _fetch_bars_multi(
        self, symbols: list[str], days: int = 260
    ) -> dict[str, list[dict]]:
        """Fetch daily bars for multiple symbols (paginated multi-symbol request)."""
        end_dt = datetime.now(timezone.utc)
        # Add 60-day buffer to account for weekends/holidays
        start_dt = end_dt - timedelta(days=days + 80)

        params = {
            "symbols": ",".join(symbols),
            "timeframe": "1Day",
            "start": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit": 1000,
            "adjustment": "all",
        }

        all_raw: dict[str, list] = {}
        page_token = None

        while True:
            if page_token:
                params["page_token"] = page_token

            data = self._get(f"{self.DATA_BASE_URL}/stocks/bars", params)
            if not data:
                break

            bars_dict = data.get("bars", {})
            for sym, bars in bars_dict.items():
                if sym not in all_raw:
                    all_raw[sym] = []
                all_raw[sym].extend(bars)

            page_token = data.get("next_page_token")
            if not page_token:
                break

        return all_raw

    # ------------------------------------------------------------------
    # Public interface (mirrors FMPClient)
    # ------------------------------------------------------------------

    def get_sp500_constituents(self) -> list[dict]:
        """Return S&P 500 constituent list with symbol, name, sector."""
        return [
            {"symbol": sym, "name": name, "sector": sector}
            for sym, name, sector in _SP500
        ]

    def get_batch_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """
        Fetch quotes for a list of symbols.

        Fetches 260-day bars in batches, computes price/yearHigh/yearLow/avgVolume,
        and caches the converted historical data for Phase 2/3 reuse.
        """
        results: dict[str, dict] = {}
        batch_size = 100  # Alpaca handles large multi-symbol requests well

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i: i + batch_size]
            raw = self._fetch_bars_multi(batch, days=260)

            for sym in batch:
                sym_raw = raw.get(sym, [])
                hist = self._convert_bars(sym_raw)
                if hist:
                    cache_key = f"hist_{sym}"
                    self.cache[cache_key] = hist
                    results[sym] = self._bars_to_quote(sym, hist)

        return results

    def get_historical_prices(self, symbol: str, days: int = 260) -> Optional[dict]:
        """Return historical prices in FMP format: {symbol, historical: [...]}."""
        cache_key = f"hist_{symbol}"
        if cache_key in self.cache:
            return {"symbol": symbol, "historical": self.cache[cache_key][:days]}

        raw = self._fetch_bars_multi([symbol], days=days)
        sym_raw = raw.get(symbol, [])
        hist = self._convert_bars(sym_raw)
        self.cache[cache_key] = hist
        return {"symbol": symbol, "historical": hist[:days]}

    def get_api_stats(self) -> dict:
        return {
            "cache_entries": len(self.cache),
            "api_calls_made": self.api_calls_made,
            "rate_limit_reached": False,
        }

    # ------------------------------------------------------------------
    # Compatibility shim — FMPClient used calculate_sma in some contexts
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_sma(prices: list[float], period: int) -> float:
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0.0
        return sum(prices[:period]) / period
