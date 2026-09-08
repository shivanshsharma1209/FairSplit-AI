FairSplit-AI
FairSplit-AI is an AI-powered bill splitting application that makes splitting restaurant bills simple and fair.
Upload a photo of a bill, let AI extract the bill details, review and correct the extracted information, add the people who shared the meal, and assign items to each person. The application then calculates each person's exact share, including GST and service charges.

Problem
Splitting a restaurant bill becomes difficult when:

Different people eat different items.
Some items are shared by multiple people.
GST and service charges must be distributed fairly.
Bills are photographed in poor lighting or at an angle.
OCR/AI may incorrectly read a value from the bill.
FairSplit-AI solves these problems by combining AI-based bill extraction with human verification and deterministic bill-splitting calculations.

Features
Upload a restaurant bill image.
Extract bill information using Gemini AI.
Extract line items, quantity, prices, subtotal, tax, service charge, discount, and total.
Show confidence scores for extracted fields.
Allow the user to review and correct AI-extracted values before calculation.
Add multiple members to the bill.
Assign an item to one person, multiple people, or everyone.
Split shared items equally or by custom proportions.
Distribute GST proportionally according to actual food consumption.
Distribute service charges proportionally according to actual food consumption.
Show a detailed per-person breakdown.
Detect and display a mismatch when the printed bill total does not match the calculated total.
How It Works
Bill Photo
    ↓
Gemini AI
    ↓
Structured Bill Data
    ↓
Pydantic Validation
    ↓
Human Review & Correction
    ↓
Assign Items to People
    ↓
Bill Splitting Calculator
    ↓
GST & Service Charge Distribution
    ↓
Final Per-Person Breakdown
Technology Stack
Python
FastAPI
Pydantic
Google Gemini API
Pillow
HTML
CSS
JavaScript
Pytest
Uvicorn
Project Structure
FairSplit-AI/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   └── services/
│       ├── __init__.py
│       ├── vision_service.py
│       └── splitter.py
│
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js
│
├── tests/
│   ├── test_splitter.py
│   └── test_api.py
│
├── .env
├── .gitignore
├── requirements.txt
└── README.md
Installation
1. Clone the repository
git clone https://github.com/shivanshsharma1209/FairSplit-AI.git
cd FairSplit-AI
2. Create a virtual environment
Windows:

py -3.12 -m venv venv
Activate it:

.\venv\Scripts\Activate.ps1
3. Install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
4. Configure Gemini API
Create a .env file in the project root:

GEMINI_API_KEY=your_api_key_here
Do not upload .env to GitHub. The included .gitignore prevents this file from being committed.

5. Run the application
python -m uvicorn app.main:app --reload --port 8000
Open:

http://127.0.0.1:8000
API Endpoints
MethodEndpointPurposeGET/healthCheck whether the backend is runningPOST/upload-billUpload and analyze a billPOST/review-billSubmit the reviewed/corrected billPOST/calculateCalculate each person's share
Bill Splitting Logic
For each person, the application first calculates the value of the food/items they consumed.
If:

Person A = ₹500
Person B = ₹300
Person C = ₹200
Food Total = ₹1000
and:

GST = ₹180
Service Charge = ₹100
then the consumption percentages are:

A = 50%
B = 30%
C = 20%
Therefore:

             Food    GST    Service    Final
Person A     ₹500    ₹90     ₹50       ₹640
Person B     ₹300    ₹54     ₹30       ₹384
Person C     ₹200    ₹36     ₹20       ₹256
This ensures GST and service charges are distributed according to what each person actually consumed rather than simply dividing them equally.

Shared Items
Shared items can be assigned to multiple people.
For example:

Pizza = ₹600
Shared by A, B and C
Equal split:

A = ₹200
B = ₹200
C = ₹200
Custom split:

A = 60%
B = 40%

A = ₹360
B = ₹240
Human Review
AI extraction is not treated as automatically correct.
Before any bill calculation takes place, the user can review extracted values and correct mistakes.
Example:

Chicken Biryani    2    ₹500    96% ✓
Coke               1    ₹80     72% ⚠
GST                     ₹94     91%
Total                   ₹674    97%

              [Confirm Bill]
This review step helps prevent an incorrect AI/OCR reading from affecting the final calculation.

Testing
Run the test suite with:

pytest
Test Dataset
The project should be tested using at least 12 real restaurant bills photographed under different conditions, including:

Dim lighting
Crumpled paper
Steep camera angle
Faded thermal printing
Handwriting
Two scripts/languages
A long bill requiring two photographs
A bill with an incorrect printed total
The ground truth for each bill should be recorded manually and compared with the AI-extracted results.

Future Improvements
Possible future improvements include:

Support for multiple bill images
Better handwritten text recognition
Improved confidence visualization
Persistent database storage
User accounts
Export results as PDF
Currency and regional tax support
Improved mobile UI
Author
Shivansh Sharma


Disclaimer
FairSplit-AI is a learning/project application. AI-extracted bill information should always be reviewed before final calculations.