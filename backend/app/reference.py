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

# Drug names in the other scheduled languages (order: PCM ORS ZNC AMX IFA MET AML ACT ASV OXY),
# used for spoken read-backs, IVR replies and recognising drug names in transcripts.
# Santali and Manipuri fall back to the English name until a native speaker adds them.
_MORE_NAMES = {
    "bn": "প্যারাসিটামল|ওআরএস|জিঙ্ক|অ্যামোক্সিসিলিন|আয়রন ফলিক অ্যাসিড|মেটফরমিন|অ্যামলোডিপিন|ম্যালেরিয়ার ওষুধ (ACT)|সাপের বিষের প্রতিষেধক|অক্সিটোসিন",
    "as": "পেৰাচিটামল|অ'আৰএছ|জিংক|এমক্সিচিলিন|আইৰন ফলিক এচিড|মেটফৰমিন|এমলডিপিন|মেলেৰিয়াৰ ঔষধ (ACT)|সাপৰ বিষৰ প্ৰতিষেধক|অক্সিটোচিন",
    "te": "పారాసిటమాల్|ఓఆర్ఎస్|జింక్|అమాక్సిసిలిన్|ఐరన్ ఫోలిక్ యాసిడ్|మెట్‌ఫార్మిన్|ఆమ్లోడిపిన్|మలేరియా మందు (ACT)|పాము విష విరుగుడు|ఆక్సిటోసిన్",
    "mr": "पॅरासिटामॉल|ओआरएस|झिंक|अमोक्सिसिलिन|आयर्न फॉलिक ॲसिड|मेटफॉर्मिन|अम्लोडिपिन|मलेरियाचे औषध (ACT)|सर्पविषरोधी लस|ऑक्सिटोसिन",
    "kok": "पॅरासिटामॉल|ओआरएस|झिंक|अमोक्सिसिलिन|आयर्न फॉलिक ॲसिड|मेटफॉर्मिन|अम्लोडिपिन|मलेरियाचें वखद (ACT)|सोरोप विखरोधी|ऑक्सिटोसिन",
    "gu": "પેરાસિટામોલ|ઓઆરએસ|ઝિંક|એમોક્સિસિલિન|આયર્ન ફોલિક એસિડ|મેટફોર્મિન|એમ્લોડિપિન|મેલેરિયાની દવા (ACT)|સાપના ઝેરની રસી|ઓક્સિટોસિન",
    "ml": "പാരസെറ്റമോൾ|ഒആർഎസ്|സിങ്ക്|അമോക്സിസിലിൻ|അയൺ ഫോളിക് ആസിഡ്|മെറ്റ്ഫോർമിൻ|അംലോഡിപിൻ|മലേറിയ മരുന്ന് (ACT)|പാമ്പുവിഷ പ്രതിവിഷം|ഓക്സിടോസിൻ",
    "pa": "ਪੈਰਾਸੀਟਾਮੋਲ|ਓਆਰਐਸ|ਜ਼ਿੰਕ|ਅਮੋਕਸੀਸਿਲਿਨ|ਆਇਰਨ ਫੋਲਿਕ ਐਸਿਡ|ਮੈਟਫਾਰਮਿਨ|ਐਮਲੋਡੀਪੀਨ|ਮਲੇਰੀਆ ਦੀ ਦਵਾਈ (ACT)|ਸੱਪ ਦੇ ਜ਼ਹਿਰ ਦੀ ਦਵਾਈ|ਆਕਸੀਟੋਸਿਨ",
    "ur": "پیراسیٹامول|او آر ایس|زنک|اموکسیسلن|آئرن فولک ایسڈ|میٹفارمن|املوڈیپین|ملیریا کی دوا (ACT)|سانپ کے زہر کا تریاق|آکسیٹوسن",
    "ks": "پیراسیٹامول|او آر ایس|زنک|اموکسیسلن|آئرن فولک ایسڈ|میٹفارمن|املوڈیپین|ملیریا دَوا (ACT)|سَرٕپ زہرُک تریاق|آکسیٹوسن",
    "sd": "پيراسيٽامول|او آر ايس|زنڪ|اموڪسيسلن|آئرن فولڪ ايسڊ|ميٽفارمن|املوڊيپين|مليريا جي دوا (ACT)|نانگ جي زهر جو ترياق|آڪسيٽوسن",
    "ne": "प्यारासिटामोल|ओआरएस|जिंक|एमोक्सिसिलिन|आइरन फोलिक एसिड|मेटफर्मिन|एम्लोडिपिन|औलोको औषधि (ACT)|सर्पविष प्रतिरोधी|अक्सिटोसिन",
    "mai": "पैरासिटामोल|ओआरएस|जिंक|एमोक्सिसिलिन|आयरन फोलिक एसिड|मेटफॉर्मिन|एम्लोडिपिन|मलेरियाक दवाइ (ACT)|साँपक विष रोधी|ऑक्सीटोसिन",
    "doi": "पैरासिटामोल|ओआरएस|जिंक|एमोक्सिसिलिन|आयरन फोलिक एसिड|मेटफॉर्मिन|एम्लोडिपिन|मलेरिया दी दवाई (ACT)|सप्प दे जैहर दी दवाई|ऑक्सीटोसिन",
    "brx": "पेरासिटामल|ओआरएस|जिंक|एमक्सिसिलिन|आइरन फलिक एसिड|मेटफरमिन|एमलडिपिन|मेलेरियानि मुलि (ACT)|जिबौनि बिस हेफाजाब|अक्सिटसिन",
    "sa": "पैरासिटामोल|ओआरएस|जिंक|एमोक्सिसिलिन|लौहफोलिकाम्लम्|मेटफॉर्मिन|एम्लोडिपिन|मलेरियौषधम् (ACT)|सर्पविषप्रतिकारकम्|ऑक्सीटोसिन",
}
for _lang, _names in _MORE_NAMES.items():
    for _d, _n in zip(DRUGS, _names.split("|"), strict=True):
        _d["names"][_lang] = _n

# State-specific epidemiology multipliers on drug rates (malaria in Odisha, snakebite in TN/KA...).
STATE_DRUG_FACTOR = {
    "OD": {"ACT": 4.0, "ORS": 1.2},
    "UP": {"ORS": 1.3, "ZNC": 1.3, "PCM": 1.1},
    "TN": {"ASV": 1.8, "MET": 1.5, "AML": 1.4},
    "KA": {"ASV": 1.6, "MET": 1.2},
}

# English + the 22 languages of the Eighth Schedule. `rtl` marks Perso-Arabic scripts.
LANGUAGES = {
    "en": {"name": "English", "native": "English", "bcp47": "en-IN"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "bcp47": "hi-IN"},
    "bn": {"name": "Bengali", "native": "বাংলা", "bcp47": "bn-IN"},
    "te": {"name": "Telugu", "native": "తెలుగు", "bcp47": "te-IN"},
    "mr": {"name": "Marathi", "native": "मराठी", "bcp47": "mr-IN"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "bcp47": "ta-IN"},
    "ur": {"name": "Urdu", "native": "اردو", "bcp47": "ur-IN", "rtl": True},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "bcp47": "gu-IN"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "bcp47": "kn-IN"},
    "or": {"name": "Odia", "native": "ଓଡ଼ିଆ", "bcp47": "or-IN"},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "bcp47": "ml-IN"},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "bcp47": "pa-IN"},
    "as": {"name": "Assamese", "native": "অসমীয়া", "bcp47": "as-IN"},
    "mai": {"name": "Maithili", "native": "मैथिली", "bcp47": "mai-IN"},
    "sat": {"name": "Santali", "native": "ᱥᱟᱱᱛᱟᱲᱤ", "bcp47": "sat-IN"},
    "ks": {"name": "Kashmiri", "native": "کٲشُر", "bcp47": "ks-IN", "rtl": True},
    "ne": {"name": "Nepali", "native": "नेपाली", "bcp47": "ne-IN"},
    "sd": {"name": "Sindhi", "native": "سنڌي", "bcp47": "sd-IN", "rtl": True},
    "kok": {"name": "Konkani", "native": "कोंकणी", "bcp47": "kok-IN"},
    "doi": {"name": "Dogri", "native": "डोगरी", "bcp47": "doi-IN"},
    "mni": {"name": "Manipuri (Meitei)", "native": "ꯃꯤꯇꯩꯂꯣꯟ", "bcp47": "mni-IN"},
    "brx": {"name": "Bodo", "native": "बड़ो", "bcp47": "brx-IN"},
    "sa": {"name": "Sanskrit", "native": "संस्कृतम्", "bcp47": "sa-IN"},
}

DRUG_BY_CODE = {d["code"]: d for d in DRUGS}
