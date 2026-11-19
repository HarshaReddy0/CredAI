"""Single source of truth for the loan application form.

The voice assistant, the typed form, the PDF form parser and the answer
normaliser all read from FIELDS, so a field is defined exactly once.
"""

SECTIONS = {
    "personal": {"en": "Personal details", "hi": "व्यक्तिगत जानकारी", "kn": "ವೈಯಕ್ತಿಕ ವಿವರಗಳು"},
    "contact": {"en": "Contact & address", "hi": "संपर्क और पता", "kn": "ಸಂಪರ್ಕ ಮತ್ತು ವಿಳಾಸ"},
    "work": {"en": "Employment & income", "hi": "रोज़गार और आय", "kn": "ಉದ್ಯೋಗ ಮತ್ತು ಆದಾಯ"},
    "loan": {"en": "Loan requirement", "hi": "ऋण आवश्यकता", "kn": "ಸಾಲದ ಅಗತ್ಯ"},
    "kyc": {"en": "KYC & assets", "hi": "केवाईसी और संपत्ति", "kn": "ಕೆವೈಸಿ ಮತ್ತು ಆಸ್ತಿ"},
}

# Each option: value (canonical, sent to the model) + display labels + spoken synonyms.
FIELDS = [
    # ---------------------------------------------------------------- personal
    {
        "key": "full_name", "section": "personal", "type": "text", "required": True,
        "label": {"en": "Full name", "hi": "पूरा नाम", "kn": "ಪೂರ್ಣ ಹೆಸರು"},
        "q": {"en": "What is your full name, as written on your PAN card?",
              "hi": "आपका पूरा नाम क्या है, जैसा पैन कार्ड पर लिखा है?",
              "kn": "ನಿಮ್ಮ ಪ್ಯಾನ್ ಕಾರ್ಡ್‌ನಲ್ಲಿರುವಂತೆ ನಿಮ್ಮ ಪೂರ್ಣ ಹೆಸರು ಏನು?"},
        "placeholder": "e.g. Ramya Shetty",
    },
    {
        "key": "dob", "section": "personal", "type": "date", "required": True,
        "label": {"en": "Date of birth", "hi": "जन्म तिथि", "kn": "ಹುಟ್ಟಿದ ದಿನಾಂಕ"},
        "q": {"en": "What is your date of birth? Please say the day, month and year.",
              "hi": "आपकी जन्म तिथि क्या है? दिन, महीना और साल बताइए।",
              "kn": "ನಿಮ್ಮ ಹುಟ್ಟಿದ ದಿನಾಂಕ ಏನು? ದಿನ, ತಿಂಗಳು ಮತ್ತು ವರ್ಷ ಹೇಳಿ."},
        "placeholder": "DD/MM/YYYY",
    },
    {
        "key": "gender", "section": "personal", "type": "select", "required": True,
        "label": {"en": "Gender", "hi": "लिंग", "kn": "ಲಿಂಗ"},
        "q": {"en": "What is your gender — male, female or other?",
              "hi": "आपका लिंग क्या है — पुरुष, महिला या अन्य?",
              "kn": "ನಿಮ್ಮ ಲಿಂಗ ಯಾವುದು — ಪುರುಷ, ಮಹಿಳೆ ಅಥವಾ ಇತರೆ?"},
        "options": [
            {"value": "F", "label": {"en": "Female", "hi": "महिला", "kn": "ಮಹಿಳೆ"},
             "syn": ["female", "woman", "lady", "girl", "महिला", "स्त्री", "औरत", "mahila", "ಮಹಿಳೆ", "ಹೆಣ್ಣು", "f"]},
            {"value": "M", "label": {"en": "Male", "hi": "पुरुष", "kn": "ಪುರುಷ"},
             "syn": ["male", "man", "boy", "gent", "पुरुष", "आदमी", "purush", "ಪುರುಷ", "ಗಂಡು", "m"]},
            {"value": "XNA", "label": {"en": "Other", "hi": "अन्य", "kn": "ಇತರೆ"},
             "syn": ["other", "non binary", "transgender", "अन्य", "ಇತರೆ", "ಇತರ"]},
        ],
    },
    {
        "key": "marital_status", "section": "personal", "type": "select", "required": True,
        "label": {"en": "Marital status", "hi": "वैवाहिक स्थिति", "kn": "ವೈವಾಹಿಕ ಸ್ಥಿತಿ"},
        "q": {"en": "What is your marital status — single, married, divorced or widowed?",
              "hi": "आपकी वैवाहिक स्थिति क्या है — अविवाहित, विवाहित, तलाकशुदा या विधवा?",
              "kn": "ನಿಮ್ಮ ವೈವಾಹಿಕ ಸ್ಥಿತಿ ಏನು — ಅವಿವಾಹಿತ, ವಿವಾಹಿತ, ವಿಚ್ಛೇದಿತ ಅಥವಾ ವಿಧವೆ?"},
        "options": [
            {"value": "Single / not married", "label": {"en": "Single", "hi": "अविवाहित", "kn": "ಅವಿವಾಹಿತ"},
             "syn": ["single", "unmarried", "not married", "bachelor", "अविवाहित", "कुंवारा", "कुंवारी", "ಅವಿವಾಹಿತ", "ಮದುವೆ ಆಗಿಲ್ಲ"]},
            {"value": "Married", "label": {"en": "Married", "hi": "विवाहित", "kn": "ವಿವಾಹಿತ"},
             "syn": ["married", "wife", "husband", "विवाहित", "शादीशुदा", "शादी", "ವಿವಾಹಿತ", "ಮದುವೆ"]},
            {"value": "Separated", "label": {"en": "Divorced / separated", "hi": "तलाकशुदा", "kn": "ವಿಚ್ಛೇದಿತ"},
             "syn": ["divorced", "separated", "तलाक", "तलाकशुदा", "ವಿಚ್ಛೇದಿತ", "ವಿಚ್ಛೇದನ"]},
            {"value": "Widow", "label": {"en": "Widowed", "hi": "विधवा / विधुर", "kn": "ವಿಧವೆ / ವಿಧುರ"},
             "syn": ["widow", "widowed", "widower", "विधवा", "विधुर", "ವಿಧವೆ", "ವಿಧುರ"]},
        ],
    },
    {
        "key": "dependents", "section": "personal", "type": "number", "required": True,
        "min": 0, "max": 15,
        "label": {"en": "Dependents", "hi": "आश्रित", "kn": "ಅವಲಂಬಿತರು"},
        "q": {"en": "How many family members depend on you financially? Say zero if none.",
              "hi": "कितने परिवार के सदस्य आर्थिक रूप से आप पर निर्भर हैं? कोई नहीं तो शून्य कहें।",
              "kn": "ಎಷ್ಟು ಕುಟುಂಬ ಸದಸ್ಯರು ಆರ್ಥಿಕವಾಗಿ ನಿಮ್ಮ ಮೇಲೆ ಅವಲಂಬಿತರು? ಯಾರೂ ಇಲ್ಲದಿದ್ದರೆ ಸೊನ್ನೆ ಹೇಳಿ."},
        "placeholder": "0",
    },
    {
        "key": "education", "section": "personal", "type": "select", "required": True,
        "label": {"en": "Education", "hi": "शिक्षा", "kn": "ಶಿಕ್ಷಣ"},
        "q": {"en": "What is your highest education — school, graduate, or post-graduate?",
              "hi": "आपकी सर्वोच्च शिक्षा क्या है — स्कूल, स्नातक या स्नातकोत्तर?",
              "kn": "ನಿಮ್ಮ ಅತ್ಯುನ್ನತ ಶಿಕ್ಷಣ ಯಾವುದು — ಶಾಲೆ, ಪದವಿ ಅಥವಾ ಸ್ನಾತಕೋತ್ತರ?"},
        "options": [
            {"value": "Lower secondary", "label": {"en": "Below 10th", "hi": "10वीं से कम", "kn": "10ನೇ ತರಗತಿಗಿಂತ ಕಡಿಮೆ"},
             "syn": ["below 10", "primary", "no education", "illiterate", "8th", "प्राथमिक", "अनपढ़", "ಪ್ರಾಥಮಿಕ"]},
            {"value": "Secondary / secondary special", "label": {"en": "10th / 12th / Diploma", "hi": "10वीं / 12वीं / डिप्लोमा", "kn": "10 / 12 / ಡಿಪ್ಲೊಮಾ"},
             "syn": ["school", "10th", "12th", "sslc", "puc", "diploma", "iti", "high school", "secondary", "स्कूल", "दसवीं", "बारहवीं", "ಶಾಲೆ", "ಪಿಯುಸಿ", "ಡಿಪ್ಲೊಮಾ"]},
            {"value": "Incomplete higher", "label": {"en": "College (not completed)", "hi": "कॉलेज (अधूरा)", "kn": "ಕಾಲೇಜು (ಪೂರ್ಣಗೊಂಡಿಲ್ಲ)"},
             "syn": ["incomplete", "dropout", "studying", "pursuing", "अधूरा", "ಅಪೂರ್ಣ"]},
            {"value": "Higher education", "label": {"en": "Graduate", "hi": "स्नातक", "kn": "ಪದವೀಧರ"},
             "syn": ["graduate", "graduation", "degree", "bachelor's", "be", "btech", "b.tech", "bcom", "bsc", "ba", "bba", "bca", "engineer", "mbbs", "स्नातक", "ग्रेजुएट", "ಪದವಿ", "ಪದವೀಧರ"]},
            {"value": "Academic degree", "label": {"en": "Post-graduate / PhD", "hi": "स्नातकोत्तर / पीएचडी", "kn": "ಸ್ನಾತಕೋತ್ತರ / ಪಿಎಚ್‌ಡಿ"},
             "syn": ["post graduate", "postgraduate", "masters", "master's", "mba", "mtech", "m.tech", "msc", "phd", "doctorate", "स्नातकोत्तर", "पीएचडी", "ಸ್ನಾತಕೋತ್ತರ"]},
        ],
    },
    # ---------------------------------------------------------------- contact
    {
        "key": "phone", "section": "contact", "type": "phone", "required": True,
        "label": {"en": "Mobile number", "hi": "मोबाइल नंबर", "kn": "ಮೊಬೈಲ್ ಸಂಖ್ಯೆ"},
        "q": {"en": "What is your ten digit mobile number?",
              "hi": "आपका दस अंकों का मोबाइल नंबर क्या है?",
              "kn": "ನಿಮ್ಮ ಹತ್ತು ಅಂಕಿಯ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ ಏನು?"},
        "placeholder": "98XXXXXXXX",
    },
    {
        "key": "email", "section": "contact", "type": "email", "required": False,
        "label": {"en": "Email (optional)", "hi": "ईमेल (वैकल्पिक)", "kn": "ಇಮೇಲ್ (ಐಚ್ಛಿಕ)"},
        "q": {"en": "What is your email address? Say skip if you don't have one.",
              "hi": "आपका ईमेल पता क्या है? न हो तो स्किप कहें।",
              "kn": "ನಿಮ್ಮ ಇಮೇಲ್ ವಿಳಾಸ ಏನು? ಇಲ್ಲದಿದ್ದರೆ ಸ್ಕಿಪ್ ಎಂದು ಹೇಳಿ."},
        "placeholder": "name@example.com",
    },
    {
        "key": "city", "section": "contact", "type": "text", "required": True,
        "label": {"en": "City", "hi": "शहर", "kn": "ನಗರ"},
        "q": {"en": "Which city or town do you live in?",
              "hi": "आप किस शहर या कस्बे में रहते हैं?",
              "kn": "ನೀವು ಯಾವ ನಗರ ಅಥವಾ ಪಟ್ಟಣದಲ್ಲಿ ವಾಸಿಸುತ್ತೀರಿ?"},
        "placeholder": "e.g. Bengaluru",
    },
    {
        "key": "state", "section": "contact", "type": "text", "required": True,
        "label": {"en": "State", "hi": "राज्य", "kn": "ರಾಜ್ಯ"},
        "q": {"en": "Which state is that in?", "hi": "वह किस राज्य में है?", "kn": "ಅದು ಯಾವ ರಾಜ್ಯದಲ್ಲಿದೆ?"},
        "placeholder": "e.g. Karnataka",
    },
    {
        "key": "pincode", "section": "contact", "type": "pincode", "required": True,
        "label": {"en": "PIN code", "hi": "पिन कोड", "kn": "ಪಿನ್ ಕೋಡ್"},
        "q": {"en": "What is your six digit PIN code?",
              "hi": "आपका छह अंकों का पिन कोड क्या है?",
              "kn": "ನಿಮ್ಮ ಆರು ಅಂಕಿಯ ಪಿನ್ ಕೋಡ್ ಏನು?"},
        "placeholder": "560001",
    },
    # ---------------------------------------------------------------- work
    {
        "key": "employment_type", "section": "work", "type": "select", "required": True,
        "label": {"en": "Employment type", "hi": "रोज़गार का प्रकार", "kn": "ಉದ್ಯೋಗದ ಪ್ರಕಾರ"},
        "q": {"en": "What do you do for a living? For example salaried, government job, business, farmer, student or retired.",
              "hi": "आप क्या काम करते हैं? जैसे नौकरी, सरकारी नौकरी, व्यापार, किसान, छात्र या सेवानिवृत्त।",
              "kn": "ನೀವು ಏನು ಕೆಲಸ ಮಾಡುತ್ತೀರಿ? ಉದಾಹರಣೆಗೆ ಸಂಬಳದ ಕೆಲಸ, ಸರ್ಕಾರಿ ಕೆಲಸ, ವ್ಯಾಪಾರ, ರೈತ, ವಿದ್ಯಾರ್ಥಿ ಅಥವಾ ನಿವೃತ್ತ."},
        "options": [
            {"value": "State servant", "label": {"en": "Government employee", "hi": "सरकारी कर्मचारी", "kn": "ಸರ್ಕಾರಿ ನೌಕರ"},
             "syn": ["government", "govt", "sarkari", "psu", "public sector", "railway", "police", "army", "teacher in government", "सरकारी", "ಸರ್ಕಾರಿ"]},
            {"value": "Working", "label": {"en": "Salaried (private)", "hi": "वेतनभोगी (निजी)", "kn": "ಸಂಬಳದ (ಖಾಸಗಿ)"},
             "syn": ["salaried", "salary", "private", "job", "employee", "employed", "it", "software", "company", "naukri", "नौकरी", "वेतन", "प्राइवेट", "ಉದ್ಯೋಗ", "ಸಂಬಳ", "ಖಾಸಗಿ", "ಕೆಲಸ"]},
            {"value": "Commercial associate", "label": {"en": "Business / self-employed", "hi": "व्यापार / स्वरोज़गार", "kn": "ವ್ಯಾಪಾರ / ಸ್ವಉದ್ಯೋಗ"},
             "syn": ["business", "self employed", "self-employed", "shop", "trader", "freelance", "consultant", "professional", "doctor", "lawyer", "व्यापार", "दुकान", "बिज़नेस", "स्वरोजगार", "ವ್ಯಾಪಾರ", "ಅಂಗಡಿ", "ಸ್ವಉದ್ಯೋಗ"]},
            {"value": "Farmer", "label": {"en": "Farmer / agriculture", "hi": "किसान / कृषि", "kn": "ರೈತ / ಕೃಷಿ"},
             "syn": ["farmer", "farming", "agriculture", "kisan", "किसान", "खेती", "ರೈತ", "ಕೃಷಿ", "ವ್ಯವಸಾಯ"]},
            {"value": "Pensioner", "label": {"en": "Retired / pensioner", "hi": "सेवानिवृत्त / पेंशनभोगी", "kn": "ನಿವೃತ್ತ / ಪಿಂಚಣಿದಾರ"},
             "syn": ["retired", "pension", "pensioner", "सेवानिवृत्त", "रिटायर", "पेंशन", "ನಿವೃತ್ತ", "ಪಿಂಚಣಿ"]},
            {"value": "Student", "label": {"en": "Student", "hi": "छात्र", "kn": "ವಿದ್ಯಾರ್ಥಿ"},
             "syn": ["student", "studying", "college", "छात्र", "विद्यार्थी", "ವಿದ್ಯಾರ್ಥಿ"]},
            {"value": "Unemployed", "label": {"en": "Not working", "hi": "बेरोज़गार", "kn": "ನಿರುದ್ಯೋಗಿ"},
             "syn": ["unemployed", "not working", "no job", "housewife", "homemaker", "बेरोजगार", "गृहिणी", "ನಿರುದ್ಯೋಗಿ", "ಗೃಹಿಣಿ"]},
        ],
    },
    {
        "key": "employer_name", "section": "work", "type": "text", "required": True,
        "depends_on": {"employment_type": ["State servant", "Working", "Commercial associate"]},
        "label": {"en": "Employer / business name", "hi": "नियोक्ता / व्यवसाय का नाम", "kn": "ಉದ್ಯೋಗದಾತ / ವ್ಯಾಪಾರದ ಹೆಸರು"},
        "q": {"en": "What is the name of your employer or business?",
              "hi": "आपके नियोक्ता या व्यवसाय का नाम क्या है?",
              "kn": "ನಿಮ್ಮ ಉದ್ಯೋಗದಾತ ಅಥವಾ ವ್ಯಾಪಾರದ ಹೆಸರು ಏನು?"},
        "placeholder": "e.g. Infosys",
    },
    {
        "key": "work_experience_years", "section": "work", "type": "number", "required": True,
        "min": 0, "max": 50,
        "depends_on": {"employment_type": ["State servant", "Working", "Commercial associate", "Farmer"]},
        "label": {"en": "Years in current work", "hi": "वर्तमान काम में वर्ष", "kn": "ಪ್ರಸ್ತುತ ಕೆಲಸದಲ್ಲಿ ವರ್ಷಗಳು"},
        "q": {"en": "How many years have you been in your current job or business?",
              "hi": "आप अपनी वर्तमान नौकरी या व्यवसाय में कितने साल से हैं?",
              "kn": "ನಿಮ್ಮ ಪ್ರಸ್ತುತ ಕೆಲಸ ಅಥವಾ ವ್ಯಾಪಾರದಲ್ಲಿ ಎಷ್ಟು ವರ್ಷಗಳಿಂದ ಇದ್ದೀರಿ?"},
        "placeholder": "e.g. 4",
    },
    {
        "key": "monthly_income", "section": "work", "type": "money", "required": True,
        "min": 0, "max": 10000000,
        "label": {"en": "Monthly income (₹)", "hi": "मासिक आय (₹)", "kn": "ಮಾಸಿಕ ಆದಾಯ (₹)"},
        "q": {"en": "What is your monthly take-home income in rupees? You can say, for example, forty five thousand.",
              "hi": "आपकी मासिक आय कितनी है? जैसे पैंतालीस हज़ार।",
              "kn": "ನಿಮ್ಮ ತಿಂಗಳ ಆದಾಯ ಎಷ್ಟು ರೂಪಾಯಿ? ಉದಾಹರಣೆಗೆ ನಲವತ್ತೈದು ಸಾವಿರ."},
        "placeholder": "e.g. 45000",
    },
    {
        "key": "existing_emi", "section": "work", "type": "money", "required": True,
        "min": 0, "max": 10000000,
        "label": {"en": "Current EMIs per month (₹)", "hi": "मौजूदा मासिक ईएमआई (₹)", "kn": "ಈಗಿನ ಮಾಸಿಕ ಇಎಂಐ (₹)"},
        "q": {"en": "How much do you already pay every month for other loans or EMIs? Say zero if none.",
              "hi": "आप दूसरे लोन या ईएमआई के लिए हर महीने कितना भरते हैं? कोई नहीं तो शून्य कहें।",
              "kn": "ಬೇರೆ ಸಾಲ ಅಥವಾ ಇಎಂಐಗಾಗಿ ತಿಂಗಳಿಗೆ ಎಷ್ಟು ಕಟ್ಟುತ್ತೀರಿ? ಇಲ್ಲದಿದ್ದರೆ ಸೊನ್ನೆ ಹೇಳಿ."},
        "placeholder": "0",
    },
    # ---------------------------------------------------------------- loan
    {
        "key": "loan_amount", "section": "loan", "type": "money", "required": True,
        "min": 10000, "max": 4000000,
        "label": {"en": "Loan amount (₹)", "hi": "ऋण राशि (₹)", "kn": "ಸಾಲದ ಮೊತ್ತ (₹)"},
        "q": {"en": "How much loan do you need, in rupees? For example, two lakh.",
              "hi": "आपको कितने रुपये का लोन चाहिए? जैसे दो लाख।",
              "kn": "ನಿಮಗೆ ಎಷ್ಟು ರೂಪಾಯಿ ಸಾಲ ಬೇಕು? ಉದಾಹರಣೆಗೆ ಎರಡು ಲಕ್ಷ."},
        "placeholder": "e.g. 200000",
    },
    {
        "key": "loan_tenure_months", "section": "loan", "type": "number", "required": True,
        "min": 6, "max": 60,
        "label": {"en": "Tenure (months)", "hi": "अवधि (महीने)", "kn": "ಅವಧಿ (ತಿಂಗಳು)"},
        "q": {"en": "Over how many months would you like to repay? Between six and sixty months.",
              "hi": "आप कितने महीनों में चुकाना चाहेंगे? छह से साठ महीने के बीच।",
              "kn": "ಎಷ್ಟು ತಿಂಗಳಲ್ಲಿ ತೀರಿಸಲು ಬಯಸುತ್ತೀರಿ? ಆರರಿಂದ ಅರವತ್ತು ತಿಂಗಳ ನಡುವೆ."},
        "placeholder": "e.g. 24",
    },
    {
        "key": "loan_purpose", "section": "loan", "type": "select", "required": True,
        "label": {"en": "Purpose", "hi": "उद्देश्य", "kn": "ಉದ್ದೇಶ"},
        "q": {"en": "What will you use this loan for? For example education, medical, home repair, business or wedding.",
              "hi": "आप इस लोन का उपयोग किसलिए करेंगे? जैसे पढ़ाई, इलाज, घर की मरम्मत, व्यापार या शादी।",
              "kn": "ಈ ಸಾಲವನ್ನು ಯಾವುದಕ್ಕೆ ಬಳಸುತ್ತೀರಿ? ಉದಾಹರಣೆಗೆ ಶಿಕ್ಷಣ, ವೈದ್ಯಕೀಯ, ಮನೆ ದುರಸ್ತಿ, ವ್ಯಾಪಾರ ಅಥವಾ ಮದುವೆ."},
        "options": [
            {"value": "education", "label": {"en": "Education", "hi": "शिक्षा", "kn": "ಶಿಕ್ಷಣ"},
             "syn": ["education", "study", "studies", "college", "school", "fees", "course", "पढ़ाई", "शिक्षा", "फीस", "ಶಿಕ್ಷಣ", "ಓದು", "ಶುಲ್ಕ"]},
            {"value": "medical", "label": {"en": "Medical", "hi": "इलाज", "kn": "ವೈದ್ಯಕೀಯ"},
             "syn": ["medical", "hospital", "treatment", "surgery", "health", "इलाज", "अस्पताल", "दवा", "ವೈದ್ಯಕೀಯ", "ಆಸ್ಪತ್ರೆ", "ಚಿಕಿತ್ಸೆ"]},
            {"value": "home_improvement", "label": {"en": "Home repair / renovation", "hi": "घर की मरम्मत", "kn": "ಮನೆ ದುರಸ್ತಿ"},
             "syn": ["home", "house", "repair", "renovation", "construction", "घर", "मरम्मत", "मकान", "ಮನೆ", "ದುರಸ್ತಿ", "ನವೀಕರಣ"]},
            {"value": "business", "label": {"en": "Business", "hi": "व्यापार", "kn": "ವ್ಯಾಪಾರ"},
             "syn": ["business", "shop", "stock", "machine", "working capital", "व्यापार", "दुकान", "ವ್ಯಾಪಾರ", "ಅಂಗಡಿ"]},
            {"value": "wedding", "label": {"en": "Wedding", "hi": "शादी", "kn": "ಮದುವೆ"},
             "syn": ["wedding", "marriage", "शादी", "विवाह", "ಮದುವೆ", "ವಿವಾಹ"]},
            {"value": "vehicle", "label": {"en": "Vehicle", "hi": "वाहन", "kn": "ವಾಹನ"},
             "syn": ["vehicle", "bike", "car", "scooter", "two wheeler", "गाड़ी", "बाइक", "ವಾಹನ", "ಬೈಕ್", "ಕಾರು"]},
            {"value": "agriculture", "label": {"en": "Agriculture", "hi": "खेती", "kn": "ಕೃಷಿ"},
             "syn": ["agriculture", "farm", "crop", "seeds", "tractor", "खेती", "फसल", "बीज", "ಕೃಷಿ", "ಬೆಳೆ", "ಬೀಜ"]},
            {"value": "debt_consolidation", "label": {"en": "Repay other loans", "hi": "दूसरे लोन चुकाने", "kn": "ಬೇರೆ ಸಾಲ ತೀರಿಸಲು"},
             "syn": ["repay", "consolidate", "credit card", "close loan", "पुराना लोन", "ಹಳೆಯ ಸಾಲ"]},
            {"value": "travel", "label": {"en": "Travel", "hi": "यात्रा", "kn": "ಪ್ರಯಾಣ"},
             "syn": ["travel", "trip", "holiday", "vacation", "यात्रा", "ಪ್ರವಾಸ", "ಪ್ರಯಾಣ"]},
            {"value": "personal", "label": {"en": "Other personal need", "hi": "अन्य निजी ज़रूरत", "kn": "ಇತರ ವೈಯಕ್ತಿಕ ಅಗತ್ಯ"},
             "syn": ["personal", "other", "family", "emergency", "अन्य", "निजी", "ಇತರೆ", "ವೈಯಕ್ತಿಕ"]},
        ],
    },
    # ---------------------------------------------------------------- KYC
    {
        "key": "pan_number", "section": "kyc", "type": "pan", "required": True,
        "label": {"en": "PAN", "hi": "पैन", "kn": "ಪ್ಯಾನ್"},
        "q": {"en": "Please tell me your PAN number — five letters, four digits and one letter. You can type it if that is easier.",
              "hi": "कृपया अपना पैन नंबर बताइए — पाँच अक्षर, चार अंक और एक अक्षर। चाहें तो टाइप भी कर सकते हैं।",
              "kn": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಪ್ಯಾನ್ ಸಂಖ್ಯೆ ಹೇಳಿ — ಐದು ಅಕ್ಷರ, ನಾಲ್ಕು ಅಂಕಿ ಮತ್ತು ಒಂದು ಅಕ್ಷರ. ಬೇಕಿದ್ದರೆ ಟೈಪ್ ಮಾಡಬಹುದು."},
        "placeholder": "ABCPK1234F",
    },
    {
        "key": "aadhaar_number", "section": "kyc", "type": "aadhaar", "required": False,
        "label": {"en": "Aadhaar (optional)", "hi": "आधार (वैकल्पिक)", "kn": "ಆಧಾರ್ (ಐಚ್ಛಿಕ)"},
        "q": {"en": "Please tell me your twelve digit Aadhaar number, or say skip. Only the last four digits are stored.",
              "hi": "अपना बारह अंकों का आधार नंबर बताइए, या स्किप कहें। केवल आखिरी चार अंक सेव होते हैं।",
              "kn": "ನಿಮ್ಮ ಹನ್ನೆರಡು ಅಂಕಿಯ ಆಧಾರ್ ಸಂಖ್ಯೆ ಹೇಳಿ, ಅಥವಾ ಸ್ಕಿಪ್ ಎನ್ನಿ. ಕೊನೆಯ ನಾಲ್ಕು ಅಂಕಿ ಮಾತ್ರ ಉಳಿಸಲಾಗುತ್ತದೆ."},
        "placeholder": "XXXX XXXX XXXX",
    },
    {
        "key": "cibil_score", "section": "kyc", "type": "number", "required": False,
        "min": 300, "max": 900,
        "label": {"en": "CIBIL score (optional)", "hi": "सिबिल स्कोर (वैकल्पिक)", "kn": "ಸಿಬಿಲ್ ಸ್ಕೋರ್ (ಐಚ್ಛಿಕ)"},
        "q": {"en": "Do you know your CIBIL credit score? It is a number between three hundred and nine hundred. Say skip if you don't know.",
              "hi": "क्या आप अपना सिबिल स्कोर जानते हैं? यह तीन सौ से नौ सौ के बीच होता है। नहीं पता तो स्किप कहें।",
              "kn": "ನಿಮ್ಮ ಸಿಬಿಲ್ ಸ್ಕೋರ್ ಗೊತ್ತೇ? ಇದು ಮುನ್ನೂರರಿಂದ ಒಂಬೈನೂರರ ನಡುವಿನ ಸಂಖ್ಯೆ. ಗೊತ್ತಿಲ್ಲದಿದ್ದರೆ ಸ್ಕಿಪ್ ಎನ್ನಿ."},
        "placeholder": "e.g. 750",
    },
    {
        "key": "own_property", "section": "kyc", "type": "boolean", "required": True,
        "label": {"en": "Owns a house / property", "hi": "मकान / संपत्ति है", "kn": "ಮನೆ / ಆಸ್ತಿ ಇದೆ"},
        "q": {"en": "Do you own a house or land? Yes or no?",
              "hi": "क्या आपके पास अपना घर या ज़मीन है? हाँ या नहीं?",
              "kn": "ನಿಮ್ಮ ಸ್ವಂತ ಮನೆ ಅಥವಾ ಜಮೀನು ಇದೆಯೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ?"},
    },
    {
        "key": "own_vehicle", "section": "kyc", "type": "boolean", "required": True,
        "label": {"en": "Owns a car", "hi": "कार है", "kn": "ಕಾರು ಇದೆ"},
        "q": {"en": "Do you own a car? Yes or no?",
              "hi": "क्या आपके पास कार है? हाँ या नहीं?",
              "kn": "ನಿಮ್ಮ ಬಳಿ ಕಾರು ಇದೆಯೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ?"},
    },
]

FIELD_MAP = {f["key"]: f for f in FIELDS}


def is_applicable(field: dict, answers: dict) -> bool:
    """A field with depends_on is only asked when the parent answer matches."""
    dep = field.get("depends_on")
    if not dep:
        return True
    for parent, allowed in dep.items():
        if answers.get(parent) not in allowed:
            return False
    return True


def public_schema(keys: list | None = None) -> dict:
    fields = FIELDS if not keys else [f for f in FIELDS if f["key"] in set(keys) or f["required"]]
    return {"sections": SECTIONS, "fields": fields}
