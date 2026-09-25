"""Reference master data: states, districts, PHC locations and the essential drug list.

District centroids and block names are real; PHC-level coordinates are jittered around
the district centroid for the prototype. Drugs follow India's National List of Essential
Medicines (NLEM) items typically stocked at a PHC.
"""

STATES = [
    {"code": "TN", "name": "Tamil Nadu", "language": "ta"},
    {"code": "KA", "name": "Karnataka", "language": "kn"},
    {"code": "UP", "name": "Uttar Pradesh", "language": "hi"},
    {"code": "OD", "name": "Odisha", "language": "or"},
]

DISTRICTS = [
    {"code": "VPM", "state": "TN", "name": "Villupuram", "lat": 11.94, "lon": 79.49,
     "blocks": ["Vanur", "Kandamangalam", "Koliyanur", "Kanai", "Mugaiyur", "Thiruvennainallur",
                "Vikravandi", "Marakkanam", "Olakkur", "Mailam", "Gingee", "Vallam",
                "Melmalayanur", "Anandapuram", "Tindivanam"]},
    {"code": "TVM", "state": "TN", "name": "Tiruvannamalai", "lat": 12.23, "lon": 79.07,
     "blocks": ["Arni", "Chengam", "Polur", "Kalasapakkam", "Thandarampattu", "Kilpennathur",
                "Vandavasi", "Cheyyar", "Jawadhu Hills", "Pudupalayam", "Thurinjapuram",
                "Vembakkam", "Anakkavoor", "Peranamallur", "Kalambur"]},
    {"code": "RCR", "state": "KA", "name": "Raichur", "lat": 16.20, "lon": 77.36,
     "blocks": ["Lingasugur", "Manvi", "Sindhanur", "Devadurga", "Maski", "Sirwar", "Mudgal",
                "Kavital", "Gabbur", "Jalahalli", "Hatti", "Yergera", "Gillesugur", "Kallur",
                "Turvihal"]},
    {"code": "KLB", "state": "KA", "name": "Kalaburagi", "lat": 17.33, "lon": 76.83,
     "blocks": ["Aland", "Afzalpur", "Chincholi", "Chittapur", "Jevargi", "Sedam", "Kamalapur",
                "Kalagi", "Shahabad", "Yadrami", "Madiyal", "Nimbarga", "Mahagaon",
                "Kadaganchi", "Farhatabad"]},
    {"code": "GKP", "state": "UP", "name": "Gorakhpur", "lat": 26.76, "lon": 83.37,
     "blocks": ["Campierganj", "Pipraich", "Chauri Chaura", "Bansgaon", "Sahjanwa", "Khajni",
                "Gola", "Barhalganj", "Bhathat", "Pali", "Jangal Kauria", "Brahmpur", "Uruwa",
                "Belghat", "Kauriram"]},
    {"code": "KSN", "state": "UP", "name": "Kushinagar", "lat": 26.74, "lon": 83.89,
     "blocks": ["Padrauna", "Kasia", "Hata", "Tamkuhi Raj", "Khadda", "Fazilnagar", "Dudhi",
                "Sukrauli", "Ramkola", "Nebua Naurangia", "Motichak", "Kaptanganj", "Seorahi",
                "Vishunpura", "Tamkuhi Road"]},
    {"code": "KRP", "state": "OD", "name": "Koraput", "lat": 18.81, "lon": 82.71,
     "blocks": ["Jeypore", "Kotpad", "Borigumma", "Boipariguda", "Kundra", "Lamtaput",
                "Nandapur", "Pottangi", "Semiliguda", "Dasamantapur", "Laxmipur",
                "Narayanpatna", "Bandhugaon", "Machkund", "Sunabeda"]},
    {"code": "RGD", "state": "OD", "name": "Rayagada", "lat": 19.17, "lon": 83.42,
     "blocks": ["Gunupur", "Bissam Cuttack", "Muniguda", "Kalyansinghpur", "Kashipur",
                "Padmapur", "Ramanaguda", "Gudari", "Kolnara", "Chandrapur", "Tikiri",
                "Ambadola", "Seskhal", "Therubali", "JK Pur"]},
]

# rate = units dispensed per OPD patient; syndrome = which footfall syndrome drives it.
DRUGS = [
    {"code": "PCM", "name": "Paracetamol 500mg", "unit": "strips", "rate": 0.30, "syndrome": "fever",
     "names": {"hi": "पैरासिटामोल", "ta": "பாராசிட்டமால்", "kn": "ಪ್ಯಾರಾಸಿಟಮಾಲ್", "or": "ପାରାସିଟାମଲ"},
     "aliases": ["paracetamol", "pcm", "crocin", "dolo", "calpol", "fever tablet", "bukhar"]},
    {"code": "ORS", "name": "ORS sachet", "unit": "sachets", "rate": 0.12, "syndrome": "diarrhoea",
     "names": {"hi": "ओआरएस", "ta": "ஓ.ஆர்.எஸ்", "kn": "ಒಆರ್‌ಎಸ್", "or": "ଓଆରଏସ"},
     "aliases": ["ors", "oral rehydration", "electral"]},
    {"code": "ZNC", "name": "Zinc 20mg dispersible", "unit": "strips", "rate": 0.05, "syndrome": "diarrhoea",
     "names": {"hi": "ज़िंक", "ta": "துத்தநாகம்", "kn": "ಜಿಂಕ್", "or": "ଜିଙ୍କ"},
     "aliases": ["zinc", "znc"]},
    {"code": "AMX", "name": "Amoxicillin 500mg", "unit": "strips", "rate": 0.10, "syndrome": "respiratory",
     "names": {"hi": "एमोक्सिसिलिन", "ta": "அமோக்சிசிலின்", "kn": "ಅಮೋಕ್ಸಿಸಿಲಿನ್", "or": "ଆମୋକ୍ସିସିଲିନ"},
     "aliases": ["amoxicillin", "amox", "amoxycillin", "antibiotic"]},
    {"code": "IFA", "name": "Iron-Folic Acid", "unit": "strips", "rate": 0.12, "syndrome": None,
     "names": {"hi": "आयरन फोलिक एसिड", "ta": "இரும்பு ஃபோலிக் அமிலம்", "kn": "ಐರನ್ ಫೋಲಿಕ್ ಆಸಿಡ್", "or": "ଆଇରନ ଫୋଲିକ ଏସିଡ"},
     "aliases": ["iron", "ifa", "folic", "iron folic"]},
    {"code": "MET", "name": "Metformin 500mg", "unit": "strips", "rate": 0.08, "syndrome": None,
     "names": {"hi": "मेटफॉर्मिन", "ta": "மெட்ஃபார்மின்", "kn": "ಮೆಟ್‌ಫಾರ್ಮಿನ್", "or": "ମେଟଫର୍ମିନ"},
     "aliases": ["metformin", "sugar tablet", "diabetes"]},
    {"code": "AML", "name": "Amlodipine 5mg", "unit": "strips", "rate": 0.07, "syndrome": None,
     "names": {"hi": "एम्लोडिपिन", "ta": "அம்லோடிபின்", "kn": "ಅಮ್ಲೋಡಿಪಿನ್", "or": "ଆମଲୋଡିପିନ"},
     "aliases": ["amlodipine", "bp tablet", "blood pressure"]},
    {"code": "ACT", "name": "Artemether-Lumefantrine (ACT)", "unit": "courses", "rate": 0.015, "syndrome": "fever",
     "names": {"hi": "मलेरिया दवा (एसीटी)", "ta": "மலேரியா மருந்து (ACT)", "kn": "ಮಲೇರಿಯಾ ಔಷಧ (ACT)", "or": "ମ୍ୟାଲେରିଆ ଔଷଧ (ACT)"},
     "aliases": ["act", "artemether", "lumefantrine", "malaria", "coartem"]},
    {"code": "ASV", "name": "Anti-Snake Venom", "unit": "vials", "rate": 0.006, "syndrome": None,
     "names": {"hi": "सांप विष रोधी (एएसवी)", "ta": "பாம்பு விஷ முறிவு மருந்து", "kn": "ಹಾವು ವಿಷ ನಿರೋಧಕ", "or": "ସାପ ବିଷ ପ୍ରତିଷେଧକ"},
     "aliases": ["asv", "anti snake venom", "snake venom", "antivenom"]},
    {"code": "OXY", "name": "Oxytocin 10IU", "unit": "ampoules", "rate": 0.010, "syndrome": None,
     "names": {"hi": "ऑक्सीटोसिन", "ta": "ஆக்ஸிடோசின்", "kn": "ಆಕ್ಸಿಟೋಸಿನ್", "or": "ଅକ୍ସିଟୋସିନ"},
     "aliases": ["oxytocin", "oxy", "pitocin"]},
]

# State-specific epidemiology multipliers on drug rates (malaria in Odisha, snakebite in TN/KA...).
STATE_DRUG_FACTOR = {
    "OD": {"ACT": 4.0, "ORS": 1.2},
    "UP": {"ORS": 1.3, "ZNC": 1.3, "PCM": 1.1},
    "TN": {"ASV": 1.8, "MET": 1.5, "AML": 1.4},
    "KA": {"ASV": 1.6, "MET": 1.2},
}

LANGUAGES = {
    "en": {"name": "English", "native": "English", "bcp47": "en-IN"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "bcp47": "hi-IN"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "bcp47": "ta-IN"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "bcp47": "kn-IN"},
    "or": {"name": "Odia", "native": "ଓଡ଼ିଆ", "bcp47": "or-IN"},
    "te": {"name": "Telugu", "native": "తెలుగు", "bcp47": "te-IN"},
    "bn": {"name": "Bengali", "native": "বাংলা", "bcp47": "bn-IN"},
    "mr": {"name": "Marathi", "native": "मराठी", "bcp47": "mr-IN"},
}

DRUG_BY_CODE = {d["code"]: d for d in DRUGS}
