# -*- coding: utf-8 -*-
"""Raw state-level data for the Claimly legal corpus catalog.
Each block: one line per jurisdiction ->  ABBR|citation|extra
Sources and verification levels are attached per topic in make_catalog.py.
"""

STATES = """AL|Alabama
AK|Alaska
AZ|Arizona
AR|Arkansas
CA|California
CO|Colorado
CT|Connecticut
DE|Delaware
DC|District of Columbia
FL|Florida
GA|Georgia
HI|Hawaii
ID|Idaho
IL|Illinois
IN|Indiana
IA|Iowa
KS|Kansas
KY|Kentucky
LA|Louisiana
ME|Maine
MD|Maryland
MA|Massachusetts
MI|Michigan
MN|Minnesota
MS|Mississippi
MO|Missouri
MT|Montana
NE|Nebraska
NV|Nevada
NH|New Hampshire
NJ|New Jersey
NM|New Mexico
NY|New York
NC|North Carolina
ND|North Dakota
OH|Ohio
OK|Oklahoma
OR|Oregon
PA|Pennsylvania
RI|Rhode Island
SC|South Carolina
SD|South Dakota
TN|Tennessee
TX|Texas
UT|Utah
VT|Vermont
VA|Virginia
WA|Washington
WV|West Virginia
WI|Wisconsin
WY|Wyoming"""

# ---------------------------------------------------------------- UDAP
# Source: NCLC, "Consumer Protection in the States", Appendix C (2018).
# Third field = statute name as printed by NCLC; names in [brackets] were NOT printed
# by NCLC under that heading and are supplied from general knowledge.
UDAP = """AL|Ala. Code §§ 8-19-1 to 8-19-15|Deceptive Trade Practices Act
AK|Alaska Stat. §§ 45.50.471 to 45.50.561|Unfair Trade Practices and Consumer Protection Act
AZ|Ariz. Rev. Stat. Ann. §§ 44-1521 to 44-1534|Consumer Fraud Act
AR|Ark. Code Ann. §§ 4-88-101 to 4-88-207|Deceptive Trade Practices Act
CA|Cal. Bus. & Prof. Code §§ 17200 to 17594; Cal. Civ. Code §§ 1750 to 1785|Unfair Competition Law; Consumers Legal Remedies Act
CO|Colo. Rev. Stat. §§ 6-1-101 to 6-1-115|Consumer Protection Act
CT|Conn. Gen. Stat. §§ 42-110a to 42-110q|Connecticut Unfair Trade Practices Act
DE|Del. Code Ann. tit. 6, §§ 2511 to 2527, 2580 to 2584|Consumer Fraud Act
DC|D.C. Code §§ 28-3901 to 28-3913|[Consumer Protection Procedures Act]
FL|Fla. Stat. §§ 501.201 to 501.213|Deceptive and Unfair Trade Practices Act
GA|Ga. Code Ann. §§ 10-1-390 to 10-1-407|Fair Business Practices Act
HI|Haw. Rev. Stat. §§ 480-1 to 480-24|[Unfair competition and unfair or deceptive acts or practices]
ID|Idaho Code Ann. §§ 48-601 to 48-619|Consumer Protection Act
IL|815 Ill. Comp. Stat. 505/1 to 505/12|Consumer Fraud and Deceptive Business Practices Act
IN|Ind. Code §§ 24-5-0.5-1 to 24-5-0.5-12|Deceptive Consumer Sales Act
IA|Iowa Code §§ 714.16 to 714.16A|[Consumer Fraud Act]
KS|Kan. Stat. Ann. §§ 50-623 to 50-640 and 50-675a to 50-679a|Consumer Protection Act
KY|Ky. Rev. Stat. Ann. §§ 367.110 to 367.990|Consumer Protection Act
LA|La. Rev. Stat. Ann. §§ 51:1401 to 51:1420|Unfair Trade Practices and Consumer Protection Law
ME|Me. Rev. Stat. Ann. tit. 5, §§ 205-A to 214|Unfair Trade Practices Act
MD|Md. Code Ann., Com. Law §§ 13-101 to 13-501|Maryland Consumer Protection Act
MA|Mass. Gen. Laws Ann. ch. 93A, §§ 1 to 11|Regulation of Business Practice and Consumer Protection Act
MI|Mich. Comp. Laws §§ 445.901 to 445.922|Consumer Protection Act
MN|Minn. Stat. § 8.31; Minn. Stat. § 325F.67; Minn. Stat. §§ 325F.68 to 325F.70|False Statement in Advertising Act; Prevention of Consumer Fraud Act
MS|Miss. Code Ann. §§ 75-24-1 to 75-24-27|Consumer Protection Act
MO|Mo. Rev. Stat. §§ 407.010 to 407.307|Merchandising Practices Act
MT|Mont. Code Ann. §§ 30-14-101 to 30-14-142|Unfair Trade Practices and Consumer Protection Act
NE|Neb. Rev. Stat. §§ 59-1601 to 59-1623|Consumer Protection Act
NV|Nev. Rev. Stat. §§ 598.0903 to 598.0999; Nev. Rev. Stat. § 41.600|Trade Regulation and Practices Act
NH|N.H. Rev. Stat. Ann. §§ 358-A:1 to 358-A:13|Consumer Protection Act
NJ|N.J. Stat. Ann. §§ 56:8-1 to 56:8-91|[Consumer Fraud Act]
NM|N.M. Stat. §§ 57-12-1 to 57-12-22|Unfair Practices Act
NY|N.Y. Exec. Law § 63(12); N.Y. Gen. Bus. Law §§ 349 and 350|[Deceptive acts and practices; false advertising]
NC|N.C. Gen. Stat. §§ 75-1.1 to 75-35|[Unfair and Deceptive Trade Practices]
ND|N.D. Cent. Code §§ 51-15-01 to 51-15-11|[Unlawful Sales or Advertising Practices]
OH|Ohio Rev. Code Ann. §§ 1345.01 to 1345.13|Consumer Sales Practices Act
OK|Okla. Stat. tit. 15, §§ 751 to 763|Consumer Protection Act
OR|Or. Rev. Stat. §§ 646.605 to 646.656|Unlawful Trade Practices Law
PA|73 Pa. Stat. Ann. §§ 201-1 to 201-9.3|Unfair Trade Practices and Consumer Protection Law
RI|R.I. Gen. Laws §§ 6-13.1-1 to 6-13.1-27|Unfair Trade Practice and Consumer Protection Act
SC|S.C. Code Ann. §§ 39-5-10 to 39-5-160|Unfair Trade Practices Act
SD|S.D. Codified Laws §§ 37-24-1 to 37-24-35|Deceptive Trade Practices and Consumer Protection Law
TN|Tenn. Code Ann. §§ 47-18-101 to 47-18-125|Consumer Protection Act
TX|Tex. Bus. & Com. Code Ann. §§ 17.41 to 17.63|Deceptive Trade Practices-Consumer Protection Act
UT|Utah Code Ann. §§ 13-11-1 to 13-11-23|Consumer Sales Practices Act
VT|Vt. Stat. Ann. tit. 9, §§ 2451 to 2480g|Consumer Fraud Act
VA|Va. Code Ann. §§ 59.1-196 to 59.1-207|Consumer Protection Act
WA|Wash. Rev. Code §§ 19.86.010 to 19.86.920|Consumer Protection Act
WV|W. Va. Code §§ 46A-6-101 to 46A-6-110|[Consumer Credit and Protection Act, art. 6]
WI|Wis. Stat. §§ 100.18, 100.20|[Fraudulent representations; methods of competition and trade practices]
WY|Wyo. Stat. Ann. §§ 40-12-101 to 40-12-114|Consumer Protection Act"""

# ---------------------------------------------------------------- LEMON LAW
# Source: Justia, "Lemon Laws: 50-State Survey" ("Applicable statute" lines).
LEMON = """AL|Ala. Code § 8-20A-1 et seq.|
AK|Alaska Stat. § 45.45.300 et seq.|
AZ|Ariz. Rev. Stat. § 44-1261 et seq.|
AR|Ark. Code § 4-90-401 et seq.|
CA|Cal. Civ. Code § 1790 et seq. (especially § 1793.2)|Song-Beverly Consumer Warranty Act; also covers consumer goods generally
CO|Colo. Rev. Stat. § 42-10-101 et seq.|
CT|Conn. Gen. Stat. § 42-179 et seq.|
DE|Del. Code tit. 6, § 5001 et seq.|
DC|D.C. Code § 50-501 et seq.|
FL|Fla. Stat. § 681.10 et seq.|
GA|Ga. Code § 10-1-780 et seq.|
HI|Haw. Rev. Stat. § 481I-1 et seq.|
ID|Idaho Code § 48-901 et seq.|
IL|815 Ill. Comp. Stat. 380/1 et seq.|
IN|Ind. Code § 24-5-13-1 et seq.|
IA|Iowa Code § 322G.1 et seq.|
KS|Kan. Stat. § 50-645 et seq.|
KY|Ky. Rev. Stat. § 367.840 et seq.|
LA|La. Rev. Stat. § 51:1941 et seq.|
ME|Me. Rev. Stat. tit. 10, § 1161 et seq.|
MD|Md. Code, Com. Law § 14-1501 et seq.; § 14-2001 et seq. (leases)|
MA|Mass. Gen. Laws ch. 90, § 7N 1/2|
MI|Mich. Comp. Laws § 257.1401 et seq.|
MN|Minn. Stat. § 325F.665|
MS|Miss. Code § 63-17-151 et seq.|
MO|Mo. Rev. Stat. § 407.560 et seq.|
MT|Mont. Code § 61-4-501 et seq.|
NE|Neb. Rev. Stat. § 60-2701 et seq.|
NV|Nev. Rev. Stat. § 597.600 et seq.|
NH|N.H. Rev. Stat. § 357-D:1 et seq.|
NJ|N.J. Rev. Stat. § 56:12-29 et seq.|
NM|N.M. Stat. § 57-16A-1 et seq.|
NY|N.Y. Gen. Bus. Law § 198-a|
NC|N.C. Gen. Stat. § 20-351 et seq.|
ND|N.D. Cent. Code § 51-07-16 et seq.|
OH|Ohio Rev. Code § 1345.71 et seq.|
OK|Okla. Stat. tit. 15, § 901 et seq.|
OR|Or. Rev. Stat. § 646A.400 et seq.|
PA|73 Pa. Stat. § 1951 et seq.|
RI|R.I. Gen. Laws § 31-5.2-1 et seq.|
SC|S.C. Code § 56-28-10 et seq.|
SD|S.D. Codified Laws § 32-6D-1 et seq.|
TN|Tenn. Code § 55-24-101 et seq.|
TX|Tex. Occ. Code § 2301.601 et seq.|
UT|Utah Code § 13-20-1 et seq.|
VT|Vt. Stat. tit. 9, § 4170 et seq.|
VA|Va. Code § 59.1-207.9 et seq.|
WA|Wash. Rev. Code § 19.118.005 et seq.|
WV|W. Va. Code § 46A-6A-1 et seq.|
WI|Wis. Stat. § 218.0171|
WY|Wyo. Stat. § 40-17-101|"""

# ---------------------------------------------------------------- GIFT CARDS
# Source: NCSL, "Gift Cards and Gift Certificates Statutes and Legislation" (table as
# republished 2026-05-20). Second field = consumer-facing provisions (definition /
# expiration / fees / cash redemption); third field = unclaimed-property (escheat)
# provisions. The split between the two fields is the catalog author's reading of the
# NCSL table, not NCSL's own column assignment -> confirm when the texts are downloaded.
GIFT = """AL||Ala. Code § 35-12-72(a)(17); § 35-12-73(b)(1)
AK||Alaska Stat. § 34.45.240; § 34.45.760
AZ|Ariz. Rev. Stat. Ann. §§ 44-7401, 44-7402|Ariz. Rev. Stat. Ann. § 44-301(17)(b)
AR|Ark. Code Ann. §§ 4-88-702 to 4-88-704|Ark. Code Ann. § 18-28-201(13)(B)
CA|Cal. Civ. Code §§ 1749.45, 1749.5|Cal. Civ. Proc. Code § 1520.5
CO|Colo. Rev. Stat. § 6-1-722|Colo. Rev. Stat. § 5-2-212; §§ 38-13-102, 38-13-207, 38-13-219
CT|Conn. Gen. Stat. §§ 42-460, 42-460a, 42-461|Conn. Gen. Stat. §§ 3-56a, 3-65c, 3-73a
DE||Del. Code Ann. tit. 12, §§ 1130, 1133
DC||D.C. Code §§ 41-151.02, 41-152.06, 41-152.07
FL|Fla. Stat. § 501.95|Fla. Stat. § 717.1045
GA|Ga. Code § 10-1-393(b)(33)|Ga. Code § 44-12-205
HI|Haw. Rev. Stat. § 481B-13|Haw. Rev. Stat. §§ 523A-3, 523A-3.5
ID||Idaho Code § 14-5-101 et seq. (incl. § 14-5-102)
IL|815 Ill. Comp. Stat. 505/2SS|765 Ill. Comp. Stat. 1026/15-101 et seq. (incl. 15-102)
IN||Ind. Code § 32-34-1.5-1 et seq. (incl. § 32-34-1.5-3)
IA||Iowa Code § 537.1301; §§ 556.1, 556.9
KS|Kan. Stat. Ann. § 50-6,108|Kan. Stat. Ann. § 58-3934
KY|Ky. Rev. Stat. § 367.890|Ky. Rev. Stat. § 393A.010 et seq.
LA|La. Rev. Stat. Ann. § 51:1423|La. Rev. Stat. Ann. §§ 9:153, 9:154
ME||Me. Rev. Stat. Ann. tit. 33, §§ 2052, 2067
MD|Md. Code Ann., Com. Law §§ 14-1319, 14-1320|Md. Code Ann., Com. Law § 17-101
MA|Mass. Gen. Laws ch. 255D, § 1; ch. 200A, § 5D; ch. 266, §§ 75C to 75F|Mass. Gen. Laws ch. 200A, § 7
MI|Mich. Comp. Laws §§ 445.903e, 445.903f, 445.903g|Mich. Comp. Laws §§ 567.222, 567.235
MN|Minn. Stat. § 325G.53|Minn. Stat. § 345.39
MS||Miss. Code Ann. §§ 89-12-3, 89-12-15
MO||Mo. Rev. Stat. § 447.505
MT|Mont. Code Ann. §§ 30-14-102, 30-14-108|Mont. Code Ann. §§ 70-9-802, 70-9-803
NE||Neb. Rev. Stat. §§ 69-1301, 69-1305.03
NV|Nev. Rev. Stat. §§ 598.0921, 598.09213|Nev. Rev. Stat. §§ 120A.077, 120A.520
NH|N.H. Rev. Stat. Ann. §§ 358-A:1, 358-A:2|N.H. Rev. Stat. Ann. §§ 471-C:1, 471-C:2, 471-C:16
NJ|N.J. Rev. Stat. § 56:8-110|N.J. Rev. Stat. §§ 46:30B-6, 46:30B-42.1, 46:30B-43.1
NM|N.M. Stat. Ann. § 57-12-26|N.M. Stat. Ann. §§ 7-8A-1, 7-8A-2(A)(7)
NY|N.Y. Gen. Bus. Law § 396-i|N.Y. Aband. Prop. Law §§ 103, 1315
NC|N.C. Gen. Stat. § 66-67.5|N.C. Gen. Stat. §§ 116B-52 to 116B-54
ND|N.D. Cent. Code §§ 51-29-01, 51-29-02|N.D. Cent. Code § 47-30.2-01 et seq.
OH|Ohio Rev. Code Ann. § 1349.61|Ohio Rev. Code Ann. § 169.01
OK|Okla. Stat. tit. 15, §§ 796, 797|Okla. Stat. tit. 60, § 651 et seq.
OR|Or. Rev. Stat. §§ 646A.274, 646A.276, 646A.278|Or. Rev. Stat. § 98.302
PA||72 Pa. Stat. §§ 1301.1, 1301.6
RI|R.I. Gen. Laws §§ 6-13-12, 6-13-12.1|R.I. Gen. Laws § 33-21.1-14
SC|S.C. Code Ann. § 39-1-55|S.C. Code Ann. § 27-18-10 et seq.
SD||S.D. Codified Laws §§ 43-41B-1, 43-41B-15, 43-41B-40, 43-41B-42, 43-41B-43
TN|Tenn. Code Ann. § 47-18-127|Tenn. Code Ann. §§ 66-29-102, 66-29-105
TX|Tex. Bus. & Com. Code §§ 604.001 to 604.152 (ch. 604)|Tex. Prop. Code Ann. §§ 72.1016, 72.103
UT|Utah Code Ann. § 13-11-4|Utah Code Ann. §§ 67-4a-101, 67-4a-102
VT|Vt. Stat. Ann. tit. 8, §§ 2701 to 2704|Vt. Stat. Ann. tit. 27, § 1251 et seq.; § 1452
VA|Va. Code §§ 59.1-530, 59.1-531|Va. Code §§ 55.1-2500, 55.1-2515
WA|Wash. Rev. Code §§ 19.240.005 to 19.240.030|Wash. Rev. Code § 63.30.010 et seq.
WV||W. Va. Code §§ 36-8-1, 36-8-2
WI||Wis. Stat. § 177.01 et seq.
WY||Wyo. Stat. §§ 34-24-102, 34-24-114"""

# ---------------------------------------------------------------- AUTOMATIC RENEWAL
# Fields: citation | scope (general / sector / none_listed) | note | verification
# Sources: MB = Practical Law / Mayer Brown chart (law stated as of 2022-06-01);
#          ZG = ZwillGen auto-renewal update (updated 2026-04-27);
#          MNREV = revisor.mn.gov (official); MODEL = catalog author's knowledge, unchecked.
AUTORENEW = """AL||none_listed||MB
AK||none_listed||MB
AZ||none_listed||MB
AR|Ark. Code Ann. § 4-86-106|sector|Home security contracts. NEW general law: 2025 Ark. HB 1820, effective 2025-08-03, modeled on California (codified section number not confirmed in this session)|MB+ZG
CA|Cal. Bus. & Prof. Code §§ 17600 to 17606|general|Amended by AB 2863, effective 2025-07-01|MB+ZG
CO|Colo. Rev. Stat. § 6-1-732|general|Amended by SB 25-145 (cancellation rules effective 2025-08-06; consumer definition 2026-02-16)|MB+ZG
CT|Conn. Gen. Stat. § 42-126b; Conn. Gen. Stat. § 21a-219 (health clubs)|general|Amended by 2026 SB 3, effective 2026-07-01 (annual reminders)|MB+ZG
DE|Del. Code tit. 6, §§ 2731 to 2737|general||MB
DC|D.C. Code § 28A-201 et seq.|general|Source chart prints the range as §§ 28A-201 to 28A-221 - confirm the end of the range at download|MB
FL|Fla. Stat. § 501.165|sector|Service, maintenance or repair contracts|MB
GA|O.C.G.A. §§ 13-12-1 to 13-12-5|sector|Service contracts|MB
HI|Haw. Rev. Stat. § 481-9.5|general||MB
ID|Idaho Code § 48-603G|general|Internet-entered subscriptions|MB
IL|815 Ill. Comp. Stat. 601/1 to 601/20|general||MB
IN||none_listed||MB
IA|Iowa Code § 552.8|sector|Physical exercise clubs only|MB
KS||none_listed||MB
KY||none_listed||MB
LA|La. Rev. Stat. § 9:2716|general|A new 'Click-to-Cancel Act' is reported to take effect 2027-01-01 (single secondary source; confirm)|MB
ME|Me. Rev. Stat. tit. 10, §§ 1210-C, 1210-D|general|Amended by 2025 SP 650, applies to agreements entered or renewed on/after 2026-01-01|MB+ZG
MD|Md. Code Ann., Com. Law § 14-12B-06|sector|Health clubs. NEW general law: 2026 Md. Laws ch. 204, effective 2026-06-01 (codified section number not confirmed in this session)|MB+ZG
MA|940 Code Mass. Regs. 38.00|general|Attorney General regulations under ch. 93A, effective 2025-09-02 (ZwillGen confirms the regulations and date; the CMR number is from the catalog author's knowledge)|ZG+MODEL
MI||none_listed||MB
MN|Minn. Stat. §§ 325G.56 to 325G.62|general|Effective 2025-01-01 (2024 c 114 art 3)|MNREV
MS||none_listed||MB
MO|Mo. Rev. Stat. § 407.675|sector|Buyers' clubs only|MB
MT|Mont. Admin. R. 38.5.6004(9), (10)|sector|Small natural gas sales service contracts only|MB
NE||none_listed||MB
NV|Nev. Rev. Stat. §§ 598.940 to 598.966|sector|Dance studios and health clubs only|MB
NH|N.H. Rev. Stat. §§ 358-I:3, 358-I:5|sector|Health clubs only|MB
NJ||none_listed||MB
NM|N.M. Admin. Code 12.2.11.1 to 12.2.11.9|sector|Service, maintenance or repair contracts (administrative rule)|MB
NY|N.Y. Gen. Bus. Law §§ 527, 527-a; N.Y. Gen. Oblig. Law § 5-903|general|Amended by 2025 S-3008 (Part W), effective 2025-11-05 (price-increase consent/cancellation)|MB+ZG
NC|N.C. Gen. Stat. § 75-41|general||MB
ND|N.D. Cent. Code §§ 51-37-01 to 51-37-06|general||MB
OH||none_listed||MB
OK||none_listed||MB
OR|Or. Rev. Stat. §§ 646A.292 to 646A.295|general||MB
PA|73 Pa. Stat. § 2164|sector|Health clubs only|MB
RI|R.I. Gen. Laws § 6-13-14|general|Rhode Island row was cut off in the source chart; citation from the catalog author's knowledge|MODEL
SC|S.C. Code Ann. § 44-79-60(4)|sector|Physical fitness contracts. A general notice regime is reported since May 2024 (citation not confirmed in this session)|MB
SD|S.D. Codified Laws § 49-31-116|sector|Telecommunications contracts only|MB
TN|Tenn. Code Ann. § 47-18-133; Tenn. Code Ann. § 62-32-325 (alarm contracts)|general|Supplemented by SB 1894, effective 2024-07-01|MB+ZG
TX||none_listed|No general automatic-renewal statute|MB
UT|Utah Code §§ 15-10-201, 15-10-202; Utah Code §§ 13-23-1 to 13-23-8 (health spas)|sector|Real-property service contracts and health spas. A broader regime is reported since 2025 (citation not confirmed in this session)|MB
VT|Vt. Stat. tit. 9, § 2454a|general|Contracts with an initial term of one year or longer|MB
VA|Va. Code Ann. §§ 59.1-207.45 to 59.1-207.49|general|Supplemented by HB 744, effective 2024-07-01|MB+ZG
WA||none_listed||MB
WV||none_listed||MB
WI|Wis. Stat. § 134.49|sector|Business contracts (equipment leases / business services), not consumer|MB
WY||none_listed||MB"""

# ---------------------------------------------------------------- SERVICE CONTRACTS
# Source: NAIC state page ST-685, Service Contracts Model Act (Fall 2021).
# Fields: citation | verification  (NAIC or MODEL)
SERVICE = """AL|Ala. Code §§ 8-32-1 to 8-32-12|NAIC
AK|Alaska Stat. § 21.03.021 (service contract is not insurance)|NAIC
AZ|Ariz. Rev. Stat. Ann. §§ 20-1095 to 20-1095.10; Ariz. Admin. Code R20-6-407|NAIC
AR|Ark. Code Ann. §§ 4-114-101 to 4-114-112; Ark. Code Ann. §§ 4-90-501 to 4-90-512 (motor vehicle service contracts)|NAIC
CA|Cal. Bus. & Prof. Code §§ 9855 to 9855.9; Cal. Civ. Code §§ 1791 to 1794.4; Cal. Ins. Code §§ 12800 to 12865 (motor vehicle service contracts); Cal. Ins. Code §§ 12140 to 12311 (motor clubs)|NAIC
CO|Colo. Rev. Stat. §§ 10-4-1601 to 10-4-1609; 3 Colo. Code Regs. § 702-5:5-1-12|NAIC
CT|Conn. Gen. Stat. § 42-260 (extended warranties)|MODEL
DE||NAIC
DC|D.C. Code Ann. §§ 31-2351.01 to 31-2351.13|NAIC
FL|Fla. Stat. §§ 634.011 to 634.271 (motor vehicle service agreements); Fla. Stat. §§ 634.301 to 634.444|NAIC
GA|Ga. Code Ann. § 33-7-6; Ga. Comp. R. & Regs. 120-2-47-.01 to 120-2-47-.14 (motor vehicle service contracts)|NAIC
HI|Haw. Rev. Stat. §§ 481X-1 to 481X-12|NAIC
ID|Idaho Code Ann. § 41-114A|NAIC
IL|215 Ill. Comp. Stat. 152/1 to 152/99|NAIC
IN|Ind. Code Ann. §§ 27-1-43.2-1 to 27-1-43.2-19|NAIC
IA|Iowa Admin. Code r. 191-103.1 to 191-103.15 (motor vehicle service contracts)|NAIC
KS||NAIC
KY|806 Ky. Admin. Regs. 5:060|NAIC
LA||NAIC
ME|Me. Rev. Stat. Ann. tit. 24-A, §§ 7101 to 7112|NAIC
MD|Md. Code Ann., Com. Law §§ 14-401 to 14-410|NAIC
MA|Mass. Gen. Laws Ann. ch. 175, § 149N|NAIC
MI||NAIC
MN|Minn. Stat. §§ 59B.01 to 59B.11|NAIC
MS|Miss. Code Ann. § 75-24-91|NAIC
MO|Mo. Rev. Stat. §§ 385.200 to 385.436 (auto); Mo. Code Regs. Ann. tit. 20, §§ 200-18.010 to 200-18.120|NAIC
MT|Mont. Code Ann. §§ 61-12-301 to 61-12-315 (motor vehicle service clubs)|NAIC
NE|Neb. Rev. Stat. §§ 44-3520 to 44-3527; Neb. Rev. Stat. §§ 44-3701 to 44-3721; 210 Neb. Admin. Code § 58 (motor vehicle service contracts)|NAIC
NV|Nev. Rev. Stat. §§ 690C.010 to 690C.330; Nev. Admin. Code §§ 690C.010 to 690C.120; Nev. Rev. Stat. §§ 696A.010 to 696A.360 (motor vehicle service clubs)|NAIC
NH|N.H. Rev. Stat. Ann. §§ 415-C:1 to 415-C:12|NAIC
NJ|N.J. Stat. Ann. § 56:12-88|NAIC
NM|N.M. Stat. Ann. §§ 59A-58-1 to 59A-58-18|NAIC
NY|N.Y. Ins. Law §§ 7901 to 7913; N.Y. Comp. Codes R. & Regs. tit. 11, §§ 390.1 to 390.13|NAIC
NC|N.C. Gen. Stat. §§ 66-370 to 66-374 (motor vehicle service and home service contracts)|NAIC
ND|N.D. Cent. Code § 9-01-21 (property service contract is not insurance)|NAIC
OH|Ohio Rev. Code Ann. § 3905.422 (home service contract is not insurance)|NAIC
OK|Okla. Stat. tit. 15, §§ 141.1 to 141.35 (service warranty); Okla. Stat. tit. 36, §§ 3101 to 3112 (motor vehicle service clubs)|NAIC
OR|Or. Rev. Stat. §§ 646A.150 to 646A.172; Or. Rev. Stat. §§ 742.390 to 742.392; Or. Admin. R. 836-200-0000 to 836-200-0060|NAIC
PA||NAIC
RI|R.I. Gen. Laws Ann. § 6-57-2 (service contracts are not insurance)|NAIC
SC|S.C. Code Ann. §§ 38-78-10 to 38-78-120; S.C. Code Ann. §§ 39-61-10 to 39-61-200 (motor club)|NAIC
SD|S.D. Codified Laws § 58-1-3 (exempts service contracts)|NAIC
TN|Tenn. Code Ann. § 56-2-126 (service contracts are not insurance)|NAIC
TX|Tex. Occ. Code ch. 1304 (Service Contract Regulatory Act)|MODEL
UT|Utah Code Ann. §§ 31A-6a-101 to 31A-6a-111; Utah Admin. Code R590-166-1 to R590-166-6|NAIC
VT|Vt. Stat. Ann. tit. 8, §§ 4247 to 4256|NAIC
VA|Va. Code Ann. §§ 59.1-435 to 59.1-441|NAIC
WA|Wash. Rev. Code Ann. §§ 48.110.010 to 48.110.904|NAIC
WV|W. Va. Code § 33-4-2 (exempts service contracts from insurance code)|NAIC
WI|Wis. Stat. §§ 616.71 to 616.82 (motor vehicle service clubs)|NAIC
WY|Wyo. Stat. Ann. §§ 26-49-101 to 26-49-111; Wyo. Stat. Ann. §§ 31-14-101 to 31-14-131 (motor vehicle service clubs)|NAIC"""

# ---------------------------------------------------------------- UNFAIR CLAIMS SETTLEMENT
# Source: NAIC state page ST-900, Unfair Claims Settlement Practices Act (Fall 2022).
# Fields: citation | verification | note
CLAIMS = """AL|Ala. Admin. Code r. 482-1-124 to 482-1-125|NAIC|
AK|Alaska Stat. § 21.36.125|NAIC|
AZ|Ariz. Rev. Stat. Ann. § 20-461|NAIC|
AR|Ark. Code Ann. § 23-66-206|NAIC|
CA|Cal. Ins. Code § 790.03; Cal. Code Regs. tit. 10, § 2695.85|NAIC|California's Fair Claims Settlement Practices Regulations sit in Cal. Code Regs. tit. 10, ch. 5, subch. 7.5 (§ 2695.1 et seq.) - download the whole subchapter
CO|Colo. Rev. Stat. § 10-3-1104|NAIC|
CT|Conn. Gen. Stat. § 38a-816|NAIC|
DE|18 Del. Admin. Code § 902|NAIC|
DC|D.C. Code § 31-2231.17|MODEL|NAIC chart lists 'no current activity' for DC; citation from the catalog author's knowledge - confirm
FL|Fla. Stat. § 626.9541; Fla. Stat. §§ 626.9743 to 626.9744 (motor vehicle settlements)|NAIC|
GA|Ga. Code Ann. §§ 33-6-30 to 33-6-37|NAIC|
HI|Haw. Rev. Stat. § 431:13-103|NAIC|
ID|Idaho Code Ann. § 41-1329|NAIC|
IL|215 Ill. Comp. Stat. 5/154.6|NAIC|
IN|Ind. Code § 27-4-1-4.5|NAIC|
IA|Iowa Code § 507B.4(3)(j)|MODEL|NAIC chart lists 'no current activity' for Iowa; citation from the catalog author's knowledge - confirm
KS|Kan. Stat. Ann. § 40-2404|NAIC|
KY|Ky. Rev. Stat. Ann. § 304.12-230|NAIC|
LA|La. Rev. Stat. Ann. § 22:1964; La. Rev. Stat. Ann. § 22:1973; La. Rev. Stat. Ann. § 22:1892|NAIC|
ME|Me. Rev. Stat. Ann. tit. 24-A, § 2164-D|NAIC|Portions of the model
MD|Md. Code Ann., Ins. §§ 27-301 to 27-306; Md. Code Regs. 31.15.08|NAIC|
MA|Mass. Gen. Laws ch. 176D, § 3|NAIC|
MI|Mich. Comp. Laws § 500.2026|NAIC|
MN|Minn. Stat. § 72A.20, subd. 12|NAIC|
MS||NAIC|NAIC chart lists 'no current activity' for Mississippi
MO|Mo. Rev. Stat. §§ 375.1000 to 375.1018|NAIC|
MT|Mont. Code Ann. § 33-18-201|NAIC|
NE|Neb. Rev. Stat. §§ 44-1536 to 44-1544|NAIC|
NV|Nev. Rev. Stat. § 686A.310|MODEL|NAIC chart lists 'no current activity' for Nevada; citation from the catalog author's knowledge - confirm
NH|N.H. Rev. Stat. Ann. § 417:4; N.H. Code Admin. R. Ins. 1001.01 to 1001.11|NAIC|
NJ|N.J. Rev. Stat. § 17:29B-4|NAIC|
NM|N.M. Stat. Ann. § 59A-16-20|NAIC|
NY|N.Y. Ins. Law § 2601|NAIC|
NC|N.C. Gen. Stat. § 58-63-15|NAIC|
ND|N.D. Cent. Code § 26.1-04-03|NAIC|
OH|Ohio Admin. Code 3901-1-07; Ohio Admin. Code 3901-1-54|NAIC|3901-1-54 comes from the NAIC property/casualty regulation chart (ST-902)
OK|Okla. Stat. tit. 36, §§ 1250.1 to 1250.16|NAIC|
OR|Or. Rev. Stat. § 746.230; Or. Admin. R. 836-080-0235|NAIC|
PA|40 Pa. Stat. Ann. § 1171.5(a)(10)|NAIC|
RI|R.I. Gen. Laws §§ 27-9.1-1 to 27-9.1-9|NAIC|
SC|S.C. Code Ann. §§ 38-59-10 to 38-59-50|NAIC|
SD|S.D. Codified Laws § 58-33-67|NAIC|
TN|Tenn. Code Ann. §§ 56-8-101 to 56-8-113|NAIC+MODEL|The extracted chart text read '58-8-101 to 58-8-113'; Tennessee's insurance law is Title 56, so the title number was corrected - confirm at download
TX|28 Tex. Admin. Code § 21.203; Tex. Ins. Code Ann. §§ 542.001 to 542.014|NAIC|
UT|Utah Code Ann. §§ 31A-26-303 to 31A-26-313|NAIC|
VT|Vt. Stat. Ann. tit. 8, § 4724|NAIC|
VA|Va. Code Ann. § 38.2-510; Va. Code Ann. § 38.2-517|NAIC|
WA|Wash. Admin. Code 284-30-300 to 284-30-390|NAIC|
WV|W. Va. Code § 33-11-4|NAIC|
WI|Wis. Admin. Code Ins. § 6.11|NAIC|
WY|Wyo. Stat. Ann. § 26-13-124|NAIC|"""

# ---------------------------------------------------------------- REFUND / RETURN POLICY DISCLOSURE
# Source: FindLaw, "Customer Returns and Refund Laws by State" (last updated 2024-01-16).
# Only states with a specific refund/return rule are listed; every other state = no specific
# statute per FindLaw (general UDAP law applies). Fields: citation | rule | verification
REFUND = """AZ|Ariz. Rev. Stat. § 44-1377|Restocking fees must be disclosed|FINDLAW
CA|Cal. Civ. Code § 1723|Refund policy must be posted unless full refund/exchange/credit is offered within 7 days; otherwise returns allowed for 30 days|FINDLAW(rule)+MODEL(citation)
CT|Conn. Gen. Stat. § 42-110aa|Retailers set their own policy; if it is not disclosed, the buyer may return goods for a refund|FINDLAW
FL|Fla. Stat. § 501.142|A no-refund policy must be displayed at the point of sale; otherwise 7-day refund right|FINDLAW
HI|Haw. Rev. Stat. § 481B-5.5|Retailers set refund policies; an improperly disclosed policy requires a refund|FINDLAW
MD||Return policy must be posted (wall, merchandise or receipt); otherwise returns within a reasonable time. FindLaw gives no citation - resolve at download|FINDLAW(rule only)
MA||Refund policy must be disclosed before the sale; otherwise returns within a reasonable time. FindLaw gives no citation - resolve at download|FINDLAW(rule only)
MN|Minn. Stat. § 325F.80|Policy must be posted in 14-point bold type; otherwise cash refunds are owed for returnable goods|FINDLAW
NJ|N.J. Stat. Ann. §§ 56:8-2.14 to 56:8-2.21|Refund policy must be posted; otherwise refund or credit up to 20 days after purchase|FINDLAW(rule)+MODEL(citation)
NY|N.Y. Gen. Bus. Law § 218-a|Refund policy must be posted; if none is posted, returns accepted within 30 days|FINDLAW(rule)+MODEL(citation)
OH||If a store has a refund policy it must be posted clearly; otherwise a refund is owed. FindLaw gives no citation - resolve at download|FINDLAW(rule only)
RI|R.I. Gen. Laws § 6-27-9|A posted notice may make all sales final; otherwise paid items are returnable within 10 business days|FINDLAW
UT||A no-refund/exchange policy must be posted; otherwise the customer may return goods. FindLaw gives no citation - resolve at download|FINDLAW(rule only)
VA|Va. Code § 59.1-200|Return policy must be posted by sign; exempt if cash or credit refunds are offered|FINDLAW"""

# ---------------------------------------------------------------- HOME SOLICITATION / DOOR-TO-DOOR COOLING-OFF
# NOT taken from a compiled 50-state source. Citations are from the catalog author's
# knowledge. SNIPPET = a search result seen in this session showed the cited statute.
# Fields: citation | verification (SNIPPET / MODEL-high / MODEL-medium)
HOMESOL = """AL|Ala. Code § 5-19-12|MODEL-medium
AK|Alaska Stat. § 45.02.350|MODEL-medium
AZ|Ariz. Rev. Stat. §§ 44-5001 to 44-5008|SNIPPET
AR|Ark. Code Ann. § 4-89-101 et seq. (incl. § 4-89-107)|SNIPPET
CA|Cal. Civ. Code §§ 1689.5 to 1689.14|MODEL-high
CO|Colo. Rev. Stat. §§ 5-3-401 to 5-3-405|MODEL-medium
CT|Conn. Gen. Stat. §§ 42-134a to 42-143|SNIPPET
DE|Del. Code tit. 6, §§ 4401 to 4405|MODEL-medium
DC|D.C. Code § 28-3811|SNIPPET
FL|Fla. Stat. §§ 501.021 to 501.055|SNIPPET
GA|O.C.G.A. § 10-1-6|MODEL-medium
HI|Haw. Rev. Stat. ch. 481C|MODEL-medium
ID|Idaho Code §§ 28-43-401 to 28-43-405|MODEL-medium
IL|815 Ill. Comp. Stat. 505/2B|MODEL-high
IN|Ind. Code ch. 24-5-10|MODEL-high
IA|Iowa Code ch. 555A|MODEL-high
KS|Kan. Stat. Ann. § 50-640|MODEL-high
KY|Ky. Rev. Stat. §§ 367.410 to 367.460|MODEL-high
LA|La. Rev. Stat. §§ 9:3538 to 9:3541|MODEL-medium
ME|Me. Rev. Stat. tit. 9-A, §§ 3-501 to 3-507|SNIPPET
MD|Md. Code Ann., Com. Law §§ 14-301 to 14-306|MODEL-high
MA|Mass. Gen. Laws ch. 93, § 48|MODEL-high
MI|Mich. Comp. Laws §§ 445.111 to 445.117|MODEL-high
MN|Minn. Stat. §§ 325G.06 to 325G.11|MODEL-high
MS|Miss. Code Ann. §§ 75-66-1 to 75-66-11|MODEL-medium
MO|Mo. Rev. Stat. §§ 407.700 to 407.720|MODEL-medium
MT|Mont. Code Ann. §§ 30-14-501 to 30-14-508|MODEL-medium
NE|Neb. Rev. Stat. §§ 69-1601 to 69-1607|MODEL-medium
NV|Nev. Rev. Stat. §§ 598.140 to 598.2801|MODEL-medium
NH|N.H. Rev. Stat. Ann. ch. 361-B|MODEL-medium
NJ|N.J. Stat. Ann. § 17:16C-61.1 et seq.|MODEL-medium
NM|N.M. Stat. Ann. § 57-12-21|MODEL-medium
NY|N.Y. Pers. Prop. Law §§ 425 to 431|MODEL-high
NC|N.C. Gen. Stat. §§ 25A-38 to 25A-42|MODEL-high
ND|N.D. Cent. Code ch. 51-18|MODEL-high
OH|Ohio Rev. Code §§ 1345.21 to 1345.28|MODEL-high
OK|Okla. Stat. tit. 14A, §§ 2-501 to 2-505|MODEL-medium
OR|Or. Rev. Stat. §§ 83.710 to 83.750|MODEL-high
PA|73 Pa. Stat. § 201-7|MODEL-high
RI|R.I. Gen. Laws ch. 6-28|MODEL-high
SC|S.C. Code Ann. §§ 37-2-501 to 37-2-506|MODEL-high
SD|S.D. Codified Laws § 37-24-5.1 et seq.|MODEL-medium
TN|Tenn. Code Ann. §§ 47-18-701 to 47-18-708|MODEL-high
TX|Tex. Bus. & Com. Code ch. 601|MODEL-high
UT|Utah Code Ann. §§ 70C-5-101 to 70C-5-106|MODEL-medium
VT|Vt. Stat. Ann. tit. 9, § 2454|SNIPPET
VA|Va. Code Ann. §§ 59.1-21.1 to 59.1-21.7:1|MODEL-high
WA|Wash. Rev. Code § 63.14.154|MODEL-medium
WV|W. Va. Code §§ 46A-2-132 to 46A-2-135|MODEL-medium
WI|Wis. Stat. §§ 423.201 to 423.205|MODEL-high
WY|Wyo. Stat. Ann. § 40-12-104; Wyo. Stat. Ann. §§ 40-14-251 to 40-14-255|MODEL-medium"""

# ---------------------------------------------------------------- UCC ARTICLE 2 WARRANTIES (as enacted)
# NOT taken from a compiled source: derived from each state's standard UCC numbering
# (official UCC §§ 2-313 to 2-318) by the catalog author. Confirm at download.
UCC2 = """AL|Ala. Code §§ 7-2-313 to 7-2-318
AK|Alaska Stat. §§ 45.02.313 to 45.02.318
AZ|Ariz. Rev. Stat. §§ 47-2313 to 47-2318
AR|Ark. Code Ann. §§ 4-2-313 to 4-2-318
CA|Cal. Com. Code §§ 2313 to 2317
CO|Colo. Rev. Stat. §§ 4-2-313 to 4-2-318
CT|Conn. Gen. Stat. §§ 42a-2-313 to 42a-2-318
DE|Del. Code tit. 6, §§ 2-313 to 2-318
DC|D.C. Code §§ 28:2-313 to 28:2-318
FL|Fla. Stat. §§ 672.313 to 672.318
GA|O.C.G.A. §§ 11-2-313 to 11-2-318
HI|Haw. Rev. Stat. §§ 490:2-313 to 490:2-318
ID|Idaho Code §§ 28-2-313 to 28-2-318
IL|810 Ill. Comp. Stat. 5/2-313 to 5/2-318
IN|Ind. Code §§ 26-1-2-313 to 26-1-2-318
IA|Iowa Code §§ 554.2313 to 554.2318
KS|Kan. Stat. Ann. §§ 84-2-313 to 84-2-318
KY|Ky. Rev. Stat. §§ 355.2-313 to 355.2-318
LA|La. Civ. Code arts. 2475, 2520 to 2548 (redhibition)
ME|Me. Rev. Stat. tit. 11, §§ 2-313 to 2-318
MD|Md. Code Ann., Com. Law §§ 2-313 to 2-318
MA|Mass. Gen. Laws ch. 106, §§ 2-313 to 2-318
MI|Mich. Comp. Laws §§ 440.2313 to 440.2318
MN|Minn. Stat. §§ 336.2-313 to 336.2-318
MS|Miss. Code Ann. §§ 75-2-313 to 75-2-318
MO|Mo. Rev. Stat. §§ 400.2-313 to 400.2-318
MT|Mont. Code Ann. §§ 30-2-313 to 30-2-318
NE|Neb. Rev. Stat. U.C.C. §§ 2-313 to 2-318
NV|Nev. Rev. Stat. §§ 104.2313 to 104.2318
NH|N.H. Rev. Stat. Ann. §§ 382-A:2-313 to 382-A:2-318
NJ|N.J. Stat. Ann. §§ 12A:2-313 to 12A:2-318
NM|N.M. Stat. Ann. §§ 55-2-313 to 55-2-318
NY|N.Y. U.C.C. Law §§ 2-313 to 2-318
NC|N.C. Gen. Stat. §§ 25-2-313 to 25-2-318
ND|N.D. Cent. Code §§ 41-02-30 to 41-02-35
OH|Ohio Rev. Code §§ 1302.26 to 1302.31
OK|Okla. Stat. tit. 12A, §§ 2-313 to 2-318
OR|Or. Rev. Stat. §§ 72.3130 to 72.3180
PA|13 Pa. Cons. Stat. §§ 2313 to 2318
RI|R.I. Gen. Laws §§ 6A-2-313 to 6A-2-318
SC|S.C. Code Ann. §§ 36-2-313 to 36-2-318
SD|S.D. Codified Laws §§ 57A-2-313 to 57A-2-318
TN|Tenn. Code Ann. §§ 47-2-313 to 47-2-318
TX|Tex. Bus. & Com. Code §§ 2.313 to 2.318
UT|Utah Code Ann. §§ 70A-2-313 to 70A-2-318
VT|Vt. Stat. Ann. tit. 9A, §§ 2-313 to 2-318
VA|Va. Code Ann. §§ 8.2-313 to 8.2-318
WA|Wash. Rev. Code §§ 62A.2-313 to 62A.2-318
WV|W. Va. Code §§ 46-2-313 to 46-2-318
WI|Wis. Stat. §§ 402.313 to 402.318
WY|Wyo. Stat. Ann. §§ 34.1-2-313 to 34.1-2-318"""

# ---------------------------------------------------------------- SMALL CLAIMS
# Source: ezel.ai survey "Small Claims Court Dollar Limits by State" (rows dated 2026-07..11).
# Third-party compilation; other 2026 compilations seen in this session disagreed on some
# figures (e.g. Arizona $3,500 vs $5,000) -> treat the dollar figure as "to confirm".
# Fields: governing law | dollar limit (individuals) | date the source says it verified
SMALLCLAIMS = """AL|Ala. Code §§ 12-12-30, 12-12-31|$6,000|2026-10-13
AK|Alaska Stat. § 22.15.040(a)|$10,000|2026-08-17
AZ|Ariz. Rev. Stat. §§ 22-501 to 22-525|$5,000|2026-10-27
AR|Ark. Code Ann. §§ 16-17-701 to 16-17-707|$5,000|2026-07-28
CA|Cal. Code Civ. Proc. §§ 116.220, 116.221|$12,500|2026-10-15
CO|Colo. Rev. Stat. §§ 13-6-401 to 13-6-417|$7,500|2026-11-09
CT|Conn. Gen. Stat. § 51-15|$5,000 (up to $15,000 for certain home improvement and new-home construction claims)|2026-10-28
DE|Del. Code tit. 10, §§ 9301, 9525, 9570, 9571|$25,000|2026-10-26
DC|D.C. Code § 11-1321|$10,000|2026-08-12
FL|Fla. Sm. Cl. R. 7.010(b)|$8,000|2026-08-23
GA|O.C.G.A. § 15-10-2(5)|$15,000|2026-08-17
HI|Haw. Rev. Stat. §§ 633-27 to 633-30|$5,000|2026-10-15
ID|Idaho Code §§ 1-2301 to 1-2315|$15,000|2026-08-17
IL|Ill. Sup. Ct. R. 281 to 289|$10,000|2026-10-27
IN|Ind. Code § 33-29-2-4|$10,000|2026-08-17
IA|Iowa Code ch. 631|$6,500|2026-08-17
KS|Kan. Stat. Ann. §§ 61-2701 to 61-2714|$10,000|2026-08-17
KY|Ky. Rev. Stat. §§ 24A.200 to 24A.360|$2,500|2026-08-13
LA|La. Rev. Stat. §§ 13:5200 to 13:5211|$5,000|2026-08-13
ME|Me. Rev. Stat. tit. 14, §§ 7481 to 7487|$10,000|2026-08-17
MD|Md. Code, Cts. & Jud. Proc. § 4-405|$5,000|2026-08-13
MA|Mass. Gen. Laws ch. 218, §§ 21 to 25|$7,000|2026-10-28
MI|Mich. Comp. Laws § 600.8401|$7,000|2026-07-09
MN|Minn. Stat. §§ 491A.01, 491A.02|$20,000 ($4,000 for consumer credit transaction claims)|2026-08-23
MS|Miss. Code Ann. § 9-11-9|$3,500|2026-08-13
MO|Mo. Rev. Stat. §§ 482.300 to 482.365|$5,000|2026-08-12
MT|Mont. Code Ann. §§ 25-35-501 to 25-35-808|$7,000|2026-08-13
NE|Neb. Rev. Stat. §§ 25-2801 to 25-2807|$7,500|2026-10-26
NV|Nev. Rev. Stat. ch. 73|$10,000|2026-10-30
NH|N.H. Rev. Stat. Ann. §§ 503:1 to 503:13|$10,000|2026-10-26
NJ|N.J. Ct. R. 6:1-2(a)(2)|$5,000|2026-07-09
NM|N.M. Stat. Ann. § 35-3-3|$10,000|2026-10-27
NY|N.Y. City Civ. Ct. Act § 1801|$10,000 (NYC Civil Court); $5,000 (other City and District Courts); $3,000 (Town/Village Justice Courts)|2026-09-09
NC|N.C. Gen. Stat. § 7A-210(1)|$10,000 statutory maximum|2026-08-12
ND|N.D. Cent. Code §§ 27-08.1-01 to 27-08.1-08|$15,000|2026-08-17
OH|Ohio Rev. Code §§ 1925.01 to 1925.02|$6,000|2026-07-09
OK|Okla. Stat. tit. 12, §§ 1751 to 1766|$10,000|2026-07-09
OR|Or. Rev. Stat. § 46.405|$10,000|2026-10-27
PA|42 Pa. Cons. Stat. § 1515(a)(3)|$12,000|2026-10-15
RI|R.I. Gen. Laws §§ 10-16-1 to 10-16-16|$5,000|2026-07-09
SC|S.C. Code § 22-3-10|$7,500|2026-08-28
SD|S.D. Codified Laws §§ 15-39-45 to 15-39-79|$12,000|2026-08-17
TN|Tenn. Code Ann. § 16-15-501(d)(1)|$25,000|2026-07-09
TX|Tex. Gov't Code § 27.031(a)(1)|$20,000|2026-10-07
UT|Utah Code §§ 78A-8-101 to 78A-8-109|$20,000|2026-08-23
VT|Vt. Stat. Ann. tit. 12, §§ 5531 to 5541|$10,000|2026-10-29
VA|Va. Code §§ 16.1-122.1 to 16.1-122.7|$5,000|2026-09-30
WA|Wash. Rev. Code ch. 12.40|$10,000|2026-08-17
WV|W. Va. Code § 50-2-1|$20,000|2026-08-13
WI|Wis. Stat. ch. 799|$10,000 (general civil actions, through 2026-12-31); $5,000 (tort/personal injury)|2026-10-29
WY|Wyo. Stat. §§ 1-21-201 to 1-21-205|$6,000|2026-08-13"""
