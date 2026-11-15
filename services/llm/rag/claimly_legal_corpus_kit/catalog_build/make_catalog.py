# -*- coding: utf-8 -*-
"""Builds the catalog CSV files of the Claimly legal corpus kit and validates them."""
import csv, json, os, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
import state_data as D

OUT = sys.argv[1] if len(sys.argv) > 1 else "catalog"
os.makedirs(OUT, exist_ok=True)

STATES = [l.split("|") for l in D.STATES.splitlines()]
ABBR = [s[0] for s in STATES]
NAME = dict(STATES)
assert len(ABBR) == 51 and len(set(ABBR)) == 51


def parse(block, nfields):
    rows = {}
    for line in block.splitlines():
        parts = line.split("|")
        assert len(parts) == nfields, (nfields, line)
        assert parts[0] in NAME, line
        assert parts[0] not in rows, "duplicate " + line
        rows[parts[0]] = [p.strip() for p in parts[1:]]
    return rows


# ------------------------------------------------------------------ topics
TOPICS = [
 # id, english name, russian name, level, claimly use, expect_terms (regex used to sanity-check downloaded text)
 ("udap", "Unfair and deceptive acts and practices (general consumer protection statute)", "Общий закон о защите потребителей (обман и недобросовестные практики)", "state", "Escalation basis for any case: denied warranty, refused refund, misleading terms", r"deceptive|unfair|unconscionable"),
 ("lemon_law", "New motor vehicle lemon law", "Lemon law: дефектный новый автомобиль", "state", "Car warranty cases; repair attempts, replacement or refund", r"motor vehicle|nonconform|manufacturer"),
 ("gift_cards", "Gift cards and gift certificates (expiration, fees, cash redemption, escheat)", "Подарочные карты и сертификаты: срок действия, комиссии, выдача остатка", "state", "Certificate module: printed expiry date vs. statutory rules; dormancy fees; cash-out of small balances", r"gift certificate|gift card|stored value"),
 ("auto_renewal", "Automatic renewal and continuous service (subscriptions)", "Автопродление подписок и отмена", "state", "Membership/subscription module: renewal notices, consent, cancellation method", r"automatic renewal|automatically renew|continuous service|renew"),
 ("service_contracts", "Service contracts and extended warranties", "Сервисные контракты и расширенные гарантии", "state", "Service-agreement module: what a provider must disclose, cancellation and refund of unused term", r"service contract|extended warranty|warranty"),
 ("unfair_claims", "Unfair insurance claims settlement practices", "Недобросовестное урегулирование страховых случаев", "state", "Insurance module: insurer duties to acknowledge, investigate and explain denials; time limits", r"claim"),
 ("refund_policy", "Retail refund and return policy disclosure", "Раскрытие правил возврата товара в магазине", "state", "Refund cases: whether a 'no refunds' policy had to be posted", r"refund|return"),
 ("home_solicitation", "Home solicitation / door-to-door sales cooling-off right", "Право отказа от покупки, сделанной на дому (cooling-off)", "state", "Cancellation cases for contracts signed at home or off-premises", r"cancel|home solicitation|door-to-door"),
 ("ucc_warranties", "UCC Article 2 warranties as enacted (express, merchantability, fitness, disclaimers)", "Гарантии по UCC Article 2: подразумеваемая гарантия качества", "state", "Warranty cases without a written warranty or after it expires; limits on disclaimers", r"warrant|merchantab"),
 ("small_claims", "Small claims court jurisdiction and dollar limit", "Суд мелких исков: лимит суммы", "state", "Last-resort next step when the company refuses; the limit decides whether the path is open", r"small claims|justice court|magistrate|district court"),
]
TOPIC_IDS = [t[0] for t in TOPICS]
EXPECT = {t[0]: t[5] for t in TOPICS}

SRC = {
 "NCLC": ("NCLC, Consumer Protection in the States, Appendix C", "2018-03", "https://www.nclc.org/images/pdf/udap/udap-appC.pdf"),
 "JUSTIA": ("Justia, Lemon Laws: 50-State Survey", "accessed 2026-11-15", "https://www.justia.com/consumer/deceptive-practices-and-fraud/lemon-laws-50-state-survey/"),
 "NCSL": ("NCSL, Gift Cards and Gift Certificates Statutes and Legislation (republished)", "2026-05-20", "https://pubt.io/view/22E07DDF0DF5ABFEA3FAFDCCE6B8B60E9230BBA5"),
 "MB": ("Practical Law / Mayer Brown, Automatic Renewal State Laws Charts: Overview", "law stated as of 2022-06-01", "https://www.mayerbrown.com/-/media/files/perspectives-events/publications/2022/07/automatic-renewal-state-laws-charts-overview.pdf"),
 "ZG": ("ZwillGen, Automatic Renewal Mid-Year Update", "updated 2026-04-27", "https://www.zwillgen.com/auto-renewal/auto-renewal-update-legal-landscape-imposes-complex-obligations-subscription-businesses/"),
 "MNREV": ("Minnesota Office of the Revisor of Statutes, Minn. Stat. 325G.56", "2024/2025 statutes", "https://www.revisor.mn.gov/statutes/2024/cite/325G.56"),
 "NAIC685": ("NAIC state page ST-685, Service Contracts Model Act", "Fall 2021", "https://content.naic.org/sites/default/files/model-law-state-page-685.pdf"),
 "NAIC900": ("NAIC state page ST-900, Unfair Claims Settlement Practices Act", "Fall 2022", "https://content.naic.org/sites/default/files/model-law-state-page-900.pdf"),
 "FINDLAW": ("FindLaw, Customer Returns and Refund Laws by State", "last updated 2024-01-16", "https://www.findlaw.com/consumer/consumer-transactions/customer-returns-and-refund-laws-by-state.html"),
 "EZEL": ("ezel.ai survey, Small Claims Court Dollar Limits by State", "rows dated 2026-07 to 2026-11", "https://ezel.ai/surveys/small-claims-court-dollar-limits"),
 "MODEL": ("Catalog author's own knowledge (Claude), not checked against a source in this session", "2026-11-15", ""),
}

# verification vocabulary (explained in README)
V_BOTH = "source+model"     # compiled source and the author's independent knowledge agree
V_SRC = "source"            # one compiled source
V_OFFICIAL = "official"     # official government page seen in this session
V_SNIP = "snippet+model"    # author's knowledge, and a search result seen in this session shows the same statute
V_MODEL_H = "model-high"    # author's knowledge only, high confidence
V_MODEL_M = "model-medium"  # author's knowledge only, medium confidence
V_NONE = "none_listed"      # the source lists no statute for this state
V_RULE = "rule_only"        # source describes a rule but gives no citation

rows = []


def add(st, topic, citation, name="", note="", related="", src="", ver=""):
    s = SRC[src]
    rows.append(collections.OrderedDict([
        ("row_id", f"{st}-{topic}"), ("state", st), ("state_name", NAME[st]), ("topic", topic),
        ("citation", citation), ("statute_name", name), ("note", note), ("related_citations", related),
        ("citation_source", s[0]), ("source_date", s[1]), ("source_url", s[2]),
        ("verification", ver), ("url", ""), ("expect_terms", EXPECT[topic]),
    ]))


udap = parse(D.UDAP, 3)
for st in ABBR:
    c, n = udap[st]
    note = ""
    if n.startswith("["):
        note = "Statute name not printed by NCLC under this heading; name supplied from general knowledge."
        n = n.strip("[]")
    if st == "IA":
        note += " Private right of action is in Iowa Code ch. 714H (author's knowledge)."
    add(st, "udap", c, n, (note + " Section ranges are as of 2018; later-added sections may extend the range.").strip(), "", "NCLC", V_BOTH)

lemon = parse(D.LEMON, 3)
for st in ABBR:
    c, n = lemon[st]
    add(st, "lemon_law", c, "", n, "", "JUSTIA", V_BOTH)

gift = parse(D.GIFT, 3)
for st in ABBR:
    c, rel = gift[st]
    note = "Consumer vs. unclaimed-property split is the catalog author's reading of the NCSL table."
    if st == "KS":
        note += " NCSL prints '§50,6108'; normalized to § 50-6,108."
    if not c:
        add(st, "gift_cards", "", "", "No dedicated consumer gift-card statute found in the NCSL table; only unclaimed-property provisions are listed. Federal floor applies: 15 U.S.C. § 1693l-1 and 12 CFR 1005.20. " + note, rel, "NCSL", V_NONE)
    else:
        add(st, "gift_cards", c, "", note, rel, "NCSL", V_SRC)

ar = parse(D.AUTORENEW, 5)
for st in ABBR:
    c, scope, note, src = ar[st]
    if scope == "none_listed":
        add(st, "auto_renewal", "", "", ("No automatic-renewal statute listed in the 2022 chart or the 2026 update consulted. " + note + " Federal ROSCA (15 U.S.C. §§ 8401-8405) and the state UDAP statute still apply. Re-check: this area changes every year.").strip(), "", "MB", V_NONE)
        continue
    ver = {"MB": V_SRC, "MB+ZG": V_SRC, "MNREV": V_OFFICIAL, "MODEL": V_MODEL_M, "ZG+MODEL": V_MODEL_M}[src]
    key = "MNREV" if src == "MNREV" else ("MODEL" if src == "MODEL" else ("ZG" if src == "ZG+MODEL" else "MB"))
    extra = " Also see ZwillGen 2026 update for the amendments noted." if "ZG" in src and key == "MB" else ""
    add(st, "auto_renewal", c, "", (f"Scope: {scope}. " + note + extra).strip(), "", key, ver)

sc = parse(D.SERVICE, 3)
for st in ABBR:
    c, src = sc[st]
    if not c:
        add(st, "service_contracts", "", "", "NAIC chart lists 'no current activity' for this state (Fall 2021). A statute may exist outside the insurance code - resolve at download.", "", "NAIC685", V_NONE)
    elif src == "MODEL":
        add(st, "service_contracts", c, "", "NAIC chart lists 'no current activity'; citation from the catalog author's knowledge - confirm.", "", "MODEL", V_MODEL_M)
    else:
        add(st, "service_contracts", c, "", "Chart column (model adoption / previous version / related activity) not preserved; parentheticals are NAIC's.", "", "NAIC685", V_SRC)

cl = parse(D.CLAIMS, 4)
for st in ABBR:
    c, src, note = cl[st]
    if not c:
        add(st, "unfair_claims", "", "", note, "", "NAIC900", V_NONE)
    elif src == "MODEL":
        add(st, "unfair_claims", c, "", note, "", "MODEL", V_MODEL_M)
    else:
        add(st, "unfair_claims", c, "", note, "", "NAIC900", V_SRC)

rf = parse(D.REFUND, 4)
for st in ABBR:
    if st not in rf:
        add(st, "refund_policy", "", "", "No specific refund-policy statute per FindLaw (2024); store policy governs and the state UDAP statute applies.", "", "FINDLAW", V_NONE)
        continue
    c, rule, src = rf[st]
    if not c:
        add(st, "refund_policy", "", "", rule, "", "FINDLAW", V_RULE)
    elif "MODEL" in src:
        add(st, "refund_policy", c, "", rule + " (Rule from FindLaw; citation from the catalog author's knowledge.)", "", "FINDLAW", V_MODEL_H)
    else:
        add(st, "refund_policy", c, "", rule, "", "FINDLAW", V_SRC)

hs = parse(D.HOMESOL, 3)
for st in ABBR:
    c, v = hs[st]
    ver = {"SNIPPET": V_SNIP, "MODEL-high": V_MODEL_H, "MODEL-medium": V_MODEL_M}[v]
    add(st, "home_solicitation", c, "", "Federal baseline: FTC Cooling-Off Rule, 16 CFR Part 429. Not taken from a compiled 50-state source.", "", "MODEL", ver)

ucc = parse(D.UCC2, 2)
for st in ABBR:
    (c,) = ucc[st]
    note = "Derived from the state's standard UCC numbering for official UCC §§ 2-313 to 2-318; also fetch the state's §§ 2-714, 2-715, 2-719 and 2-725 (remedies, limitation of remedy, statute of limitations)."
    if st == "LA":
        note = "Louisiana has not enacted UCC Article 2; the Civil Code's warranty against redhibitory defects plays this role."
    if st == "CA":
        note += " California did not enact § 2-318."
    add(st, "ucc_warranties", c, "", note, "", "MODEL", V_MODEL_H)

sm = parse(D.SMALLCLAIMS, 4)
for st in ABBR:
    c, limit, dt = sm[st]
    add(st, "small_claims", c, "", f"Dollar limit per source: {limit} (source says verified {dt}). Third-party compilation; limits change - confirm on the state court website before showing to users.", "", "EZEL", V_SRC)

# ------------------------------------------------------------------ validation
by_topic = collections.defaultdict(set)
for r in rows:
    by_topic[r["topic"]].add(r["state"])
for t in TOPIC_IDS:
    assert by_topic[t] == set(ABBR), (t, set(ABBR) - by_topic[t])
assert len(rows) == 51 * len(TOPIC_IDS)
assert len({r["row_id"] for r in rows}) == len(rows)

with open(os.path.join(OUT, "state_sources.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

with open(os.path.join(OUT, "topics.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["topic", "name_en", "name_ru", "level", "claimly_use", "expect_terms"])
    w.writerows(TOPICS)

# ------------------------------------------------------------------ federal
FED_USC = [
 # id, title, sections spec, name, topic, priority, claimly use, status note, verification
 ("USC-01", 15, "2301..2312", "Magnuson-Moss Warranty Act", "warranty", 1, "Written warranties: disclosure, 'full' vs 'limited', no tie-in sales, limits on disclaiming implied warranties, right to sue", "", V_MODEL_H),
 ("USC-02", 15, "45", "FTC Act § 5 (unfair or deceptive acts or practices)", "consumer_protection", 1, "Federal baseline behind every state UDAP law", "", V_MODEL_H),
 ("USC-03", 15, "45b", "Consumer Review Fairness Act", "contract_terms", 2, "Form-contract clauses that ban or penalize customer reviews are void", "", V_MODEL_H),
 ("USC-04", 15, "57b", "FTC Act § 19 (consumer redress after rule violations)", "consumer_protection", 3, "Background on remedies for FTC rule violations", "", V_MODEL_H),
 ("USC-05", 15, "8401..8405", "Restore Online Shoppers' Confidence Act (ROSCA)", "subscriptions", 1, "Online negative-option subscriptions: disclosure, consent, simple cancellation. Main federal tool after the click-to-cancel rule was vacated", "", V_MODEL_H),
 ("USC-06", 15, "1693..1693r", "Electronic Fund Transfer Act (incl. § 1693l-1 gift cards, § 1693e preauthorized transfers, § 1693f error resolution, § 1693g consumer liability)", "payments_gift_cards", 1, "Gift card expiry (5-year floor) and fees; stopping recurring debits; disputing debit-card errors", "", V_MODEL_H),
 ("USC-07", 15, "1666..1666j", "Fair Credit Billing Act (incl. § 1666i claims and defenses against card issuer)", "payments", 1, "Credit-card billing disputes when goods or services were not delivered as agreed", "", V_MODEL_H),
 ("USC-08", 15, "1643", "Truth in Lending Act § 133 (liability of cardholder)", "payments", 2, "Limits on liability for unauthorized credit-card use", "", V_MODEL_H),
 ("USC-09", 15, "7001..7006", "E-SIGN Act", "contract_terms", 2, "Validity of electronic contracts and conditions for electronic consumer disclosures", "", V_MODEL_H),
 ("USC-10", 9, "1..16", "Federal Arbitration Act, chapter 1", "contract_terms", 2, "Arbitration clauses in terms and conditions", "", V_MODEL_H),
 ("USC-11", 15, "1011..1015", "McCarran-Ferguson Act", "insurance", 3, "Why insurance is regulated mainly by the states", "", V_MODEL_H),
 ("USC-12", 42, "300gg-13", "Public Health Service Act § 2713 (ACA preventive services without cost sharing)", "insurance", 1, "Free preventive care already paid for through the premium", "", V_MODEL_H),
 ("USC-13", 42, "300gg-19", "Public Health Service Act § 2719 (internal appeals and external review)", "insurance", 1, "Right to appeal a health-plan denial", "", V_MODEL_H),
 ("USC-14", 42, "300gg-111;300gg-131;300gg-132", "No Surprises Act (core sections)", "insurance", 2, "Surprise out-of-network bills", "Other sections of the Act exist; extend the list after reviewing the downloaded title", V_MODEL_H),
 ("USC-15", 29, "1133", "ERISA § 503 (claims procedure)", "insurance", 1, "Employer-plan claim denials: written reasons and a full and fair review", "", V_MODEL_H),
 ("USC-16", 49, "41712", "Unfair and deceptive practices in air transportation", "travel", 2, "DOT authority behind airline refund and bumping rules", "", V_MODEL_H),
 ("USC-17", 49, "42305", "Refunds for cancelled or significantly delayed or changed flights (FAA Reauthorization Act of 2024)", "travel", 1, "Statutory airline refund right", "Section number taken from a secondary source seen in this session; confirm when title 49 is downloaded", V_SRC),
 ("USC-18", 49, "30120", "Motor vehicle safety recall remedies", "auto", 1, "Recall repairs must be provided without charge", "", V_MODEL_H),
 ("USC-19", 42, "7541", "Clean Air Act § 207 (emission control warranties)", "auto", 2, "Federal emissions warranty on vehicle components", "", V_MODEL_H),
 ("USC-20", 39, "3009", "Mailing of unordered merchandise", "contract_terms", 2, "Unordered merchandise may be treated as a gift", "", V_MODEL_H),
 ("USC-21", 15, "2064", "Consumer Product Safety Act § 15 (substantial product hazards; repair, replacement or refund)", "recalls", 3, "Recall remedies for consumer products (future module)", "", V_MODEL_H),
 ("USC-22", 15, "6101..6108", "Telemarketing and Consumer Fraud and Abuse Prevention Act", "consumer_protection", 3, "Statutory basis of the Telemarketing Sales Rule", "", V_MODEL_H),
]
FED_CFR = [
 # id, title, part, subpart, sections, name, topic, priority, use, status note
 ("CFR-01", 16, "700", "", "", "Interpretations of Magnuson-Moss Warranty Act", "warranty", 1, "FTC's reading of the Warranty Act (e.g. tie-in sales, duration)", ""),
 ("CFR-02", 16, "701", "", "", "Disclosure of Written Consumer Product Warranty Terms and Conditions", "warranty", 1, "What a written warranty must state", ""),
 ("CFR-03", 16, "702", "", "", "Pre-Sale Availability of Written Warranty Terms", "warranty", 1, "Seller must make warranty terms available before purchase", ""),
 ("CFR-04", 16, "703", "", "", "Informal Dispute Settlement Procedures", "warranty", 2, "Rules for warranty dispute programs", ""),
 ("CFR-05", 16, "239", "", "", "Guides for the Advertising of Warranties and Guarantees", "warranty", 2, "'Satisfaction guaranteed', 'lifetime' and similar claims", ""),
 ("CFR-06", 16, "251", "", "", "Guide Concerning Use of the Word 'Free' and Similar Representations", "contract_terms", 2, "When an offer may be called free", ""),
 ("CFR-07", 16, "425", "", "", "Use of Prenotification Negative Option Plans", "subscriptions", 1, "Federal negative-option rule", "The 2024 'click-to-cancel' amendments were vacated by the Eighth Circuit on 2025-07-08 (Custom Communications v. FTC). FTC issued an ANPRM on 2026-03-11. Check which text eCFR shows on the download date; do not present click-to-cancel as in force."),
 ("CFR-08", 16, "429", "", "", "Cooling-Off Period for Sales Made at Homes or at Certain Other Locations", "cancellation", 1, "Three-business-day right to cancel door-to-door sales", ""),
 ("CFR-09", 16, "435", "", "", "Mail, Internet, or Telephone Order Merchandise", "refunds", 1, "Shipping deadlines; right to cancel and get a prompt refund when the seller is late", ""),
 ("CFR-10", 16, "310", "", "", "Telemarketing Sales Rule", "consumer_protection", 3, "Telemarketing refunds and disclosures", ""),
 ("CFR-11", 16, "433", "", "", "Preservation of Consumers' Claims and Defenses (Holder Rule)", "payments", 2, "Claims against the lender when a financed purchase goes wrong", ""),
 ("CFR-12", 16, "455", "", "", "Used Motor Vehicle Trade Regulation Rule", "auto", 2, "Buyers Guide; 'as is' vs warranty on used cars", ""),
 ("CFR-13", 16, "464", "", "", "Rule on Unfair or Deceptive Fees", "contract_terms", 2, "Total-price disclosure for live-event tickets and short-term lodging", "Effective 2025-05-12; scope limited to live-event tickets and short-term lodging."),
 ("CFR-14", 12, "1005", "", "", "Regulation E (Electronic Fund Transfers), incl. § 1005.20 gift cards and official interpretations", "payments_gift_cards", 1, "Gift card rules in detail; error resolution; recurring debits", "Large part (includes Supplement I)."),
 ("CFR-15", 12, "1026", "", "1026.12;1026.13", "Regulation Z, §§ 1026.12 (special credit card provisions) and 1026.13 (billing error resolution)", "payments", 1, "Credit-card dispute procedure and deadlines", "Only two sections are requested; the full part is very large."),
 ("CFR-16", 14, "250", "", "", "Oversales (denied boarding compensation)", "travel", 2, "Compensation for involuntary bumping", ""),
 ("CFR-17", 14, "254", "", "", "Domestic Baggage Liability", "travel", 3, "Minimum liability limit for lost or damaged bags", ""),
 ("CFR-18", 14, "259", "", "", "Enhanced Protections for Airline Passengers", "travel", 2, "Customer service plans, tarmac delays, refund processing", ""),
 ("CFR-19", 14, "260", "", "", "Refunds for Airline Fare and Ancillary Service Fees", "travel", 1, "Automatic refunds for cancelled or significantly changed flights", "In effect. DOT is not enforcing the refund requirement where a flight is merely renumbered (notice extended on 2026-07-07 to 2027-07-07) and has an open 'Refund III' rulemaking."),
 ("CFR-20", 45, "147", "", "147.130;147.136", "Health insurance market rules: § 147.130 preventive services; § 147.136 claims, appeals and external review", "insurance", 1, "Free preventive services; how to appeal a denial", ""),
 ("CFR-21", 45, "149", "", "", "Surprise Billing and Transparency Requirements", "insurance", 3, "No Surprises Act regulations", "Large part; optional for the MVP."),
 ("CFR-22", 29, "2560", "", "2560.503-1", "ERISA claims procedure regulation", "insurance", 1, "Deadlines and content of benefit denials and appeals", ""),
 ("CFR-23", 40, "85", "V", "", "Emissions Control System Performance Warranty Regulations", "auto", 3, "Detail on the federal emissions warranty", "Subpart letter from the catalog author's knowledge; confirm against the part's table of contents."),
 ("CFR-24", 49, "577", "", "", "Defect and Noncompliance Notification", "auto", 3, "What a vehicle recall notice must say", ""),
 ("CFR-25", 49, "375", "", "", "Transportation of Household Goods in Interstate Commerce; Consumer Protection Regulations", "moving", 3, "Moving-company estimates and loss/damage claims", ""),
]
fed = []
for (i, t, secs, name, topic, pr, use, status, ver) in FED_USC:
    first = secs.split(";")[0].split("..")[0]
    fed.append(collections.OrderedDict([
        ("id", i), ("kind", "statute"), ("citation", f"{t} U.S.C. " + secs.replace("..", " to ").replace(";", ", ")),
        ("name", name), ("topic", topic), ("priority", pr), ("claimly_use", use), ("status_note", status),
        ("source_system", "uscode"), ("title", t), ("part", ""), ("subpart", ""), ("sections", secs),
        ("human_url", f"https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title{t}-section{first}&num=0&edition=prelim"),
        ("verification", ver),
    ]))
for (i, t, part, sub, secs, name, topic, pr, use, status) in FED_CFR:
    cit = f"{t} CFR Part {part}" + (f", Subpart {sub}" if sub else "") + (" (" + ", ".join("§ " + s for s in secs.split(";")) + ")" if secs else "")
    fed.append(collections.OrderedDict([
        ("id", i), ("kind", "regulation"), ("citation", cit), ("name", name), ("topic", topic), ("priority", pr),
        ("claimly_use", use), ("status_note", status), ("source_system", "ecfr"), ("title", t), ("part", part),
        ("subpart", sub), ("sections", secs), ("human_url", f"https://www.ecfr.gov/current/title-{t}/part-{part}"),
        ("verification", V_MODEL_H),
    ]))
assert len({r["id"] for r in fed}) == len(fed)
with open(os.path.join(OUT, "federal_sources.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(fed[0].keys()))
    w.writeheader(); w.writerows(fed)

# ------------------------------------------------------------------ datasets and guidance
DS = [
 # name, type, what, url, licence/terms note, checked this session, claimly use
 ("eCFR API (Office of the Federal Register / GPO)", "primary source", "Current text of every federal regulation as XML; no API key", "https://www.ecfr.gov/api/versioner/v1/titles.json", "US government work", "yes (endpoint paths confirmed in search results; not called from the sandbox)", "Used by scripts/download_federal.py"),
 ("eCFR developer resources", "documentation", "Explains the API and the meaning of eCFR dates", "https://www.ecfr.gov/reader-aids/ecfr-developer-resources", "US government work", "yes", "Read before changing the downloader"),
 ("U.S. Code release points (Office of the Law Revision Counsel)", "primary source", "Each title of the U.S. Code as USLM XML, updated per public law", "https://uscode.house.gov/download/download.shtml", "US government work", "yes (release point pages seen in search results; latest seen: Public Law 119-102)", "Used by scripts/download_federal.py"),
 ("CFPB Consumer Complaint Database", "dataset", "Millions of consumer complaints about financial products with company responses; some with narratives", "https://www.consumerfinance.gov/data-research/consumer-complaints/", "US government work; see site terms", "no (URL from the catalog author's knowledge)", "Examples of how consumers describe problems and how companies answer (financial products only)"),
 ("CFPB credit card agreements database", "dataset", "Actual cardholder agreements filed by issuers", "https://www.consumerfinance.gov/credit-cards/agreements/", "Agreements are issuers' documents published by the CFPB; see site terms", "no (URL from the catalog author's knowledge)", "Real terms and conditions; card benefits such as purchase protection are usually in separate benefit guides"),
 ("FTC consumer advice articles", "guidance", "Plain-language articles on warranties, service contracts, gift cards, returns, subscriptions", "https://consumer.ftc.gov/", "US government work", "no (URL from the catalog author's knowledge)", "Best material for user-facing explanations; cite alongside the statute"),
 ("FTC Rule on Unfair or Deceptive Fees: FAQ", "guidance", "FTC staff FAQ on 16 CFR Part 464", "https://www.ftc.gov/business-guidance/resources/rule-unfair-or-deceptive-fees-frequently-asked-questions", "US government work", "yes", "Explains the fees rule"),
 ("DOT: What airline passengers need to know about the automatic refund rule", "guidance", "DOT explanation of 14 CFR Part 260", "https://www.transportation.gov/briefing-room/what-airline-passengers-need-know-about-dots-automatic-refund-rule", "US government work", "yes", "Airline refund cases"),
 ("Federal Register 2026-13675 (DOT enforcement discretion, renumbered flights)", "status notice", "Extends the enforcement pause to 2027-07-07", "https://www.federalregister.gov/documents/2026/07/07/2026-13675/airline-refunds-and-other-consumer-protections", "US government work", "yes", "Needed so the assistant does not overstate airline refund rights"),
 ("USA.gov state consumer protection offices", "directory", "Where to complain in each state", "https://www.usa.gov/state-consumer", "US government work", "no (URL from the catalog author's knowledge)", "Next-step suggestions"),
 ("NAIC state insurance departments", "directory", "Insurance regulator for each state", "https://content.naic.org/state-insurance-departments", "NAIC site terms apply", "no (URL from the catalog author's knowledge)", "Next step for insurance complaints"),
 ("NAIC state page ST-76, Uniform Health Carrier External Review Model Act", "reference chart", "State external-review laws for health-plan denials (Summer 2025)", "https://content.naic.org/sites/default/files/model-law-state-page-76.pdf", "(c) NAIC; use as a lookup aid", "yes (seen in search results; not extracted)", "Add as an eleventh state topic in phase 2"),
 ("NCLC Compendium of Used Car Warranty Laws (January 2026)", "reference", "State used-car warranty statutes", "https://www.nclc.org/wp-content/uploads/2026/01/202601_White-Paper_Compendium-of-Used-Car-Warranty-Laws.pdf", "(c) NCLC; use as a lookup aid", "yes (seen in search results; not extracted)", "Add used-car warranty laws in phase 2"),
 ("Multi_Legal_Pile_Commercial (Hugging Face, joelniklaus)", "dataset", "Legal text corpus limited to data described as permissively licensed for commercial use; includes US Code, CFR and state codes snapshots", "https://huggingface.co/datasets/joelniklaus/Multi_Legal_Pile_Commercial", "Stated by the dataset card as commercial-use friendly; read the card. Snapshot is several years old", "yes", "Fallback bulk source for state codes if official sites cannot be scraped; NOT current law"),
 ("Pile of Law (Hugging Face, pile-of-law)", "dataset", "256 GB US legal corpus incl. state_codes, uscode, cfr, tos, cfpb_creditcard_contracts", "https://huggingface.co/datasets/pile-of-law/pile-of-law", "CC BY-NC-SA 4.0 = non-commercial. Not suitable for a commercial product without clearing the licence", "yes", "Do not use in the product as is"),
 ("FTC press release: final order against DoNotPay ('robot lawyer')", "enforcement example", "FTC order over unsubstantiated 'AI lawyer' claims (finalized early 2025)", "https://www.ftc.gov/news-events/news/press-releases/2025/02/ftc-finalizes-order-donotpay-prohibits-deceptive-ai-lawyer-claims-imposes-monetary-relief-requires", "US government work", "yes", "For the team, not for the corpus: how Claimly may describe its AI"),
]
with open(os.path.join(OUT, "datasets_and_guidance.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["name", "type", "what_it_is", "url", "licence_or_terms_note", "url_checked_this_session", "claimly_use"])
    w.writerows(DS)

# ------------------------------------------------------------------ stats
ver_counts = collections.Counter(r["verification"] for r in rows)
topic_ver = collections.defaultdict(collections.Counter)
for r in rows:
    topic_ver[r["topic"]][r["verification"]] += 1
stats = {
    "state_rows": len(rows), "jurisdictions": 51, "state_topics": len(TOPIC_IDS),
    "state_rows_with_citation": sum(1 for r in rows if r["citation"]),
    "state_rows_by_verification": dict(ver_counts),
    "by_topic": {t: dict(c) for t, c in topic_ver.items()},
    "federal_rows": len(fed), "federal_statutes": len(FED_USC), "federal_regulations": len(FED_CFR),
    "datasets_rows": len(DS),
}
with open(os.path.join(OUT, "catalog_stats.json"), "w", encoding="utf-8") as f:
    json.dump(stats, f, indent=2, ensure_ascii=False)
print(json.dumps(stats, indent=2, ensure_ascii=False))
