"""
Ground-truth test cases for the Bloodhound evaluation harness.

GOLDEN_EXTRACTIONS: list of {cv_text, expected} dicts used to score
  CV parsing accuracy. Each 'expected' dict maps field names (matching
  CandidateExtraction attributes) to their correct values.

GOLDEN_MATCHES: list of {requirement, candidates, expected_winner_index} dicts.
  'candidates' are minimal profile dicts fed directly into scoring functions.
  'expected_winner_index' is the index of the candidate that should rank #1.
  A test passes when the top-scored candidate matches the expected winner.
"""

GOLDEN_EXTRACTIONS = [
    {
        "cv_text": (
            "Jane Smith\n"
            "jane.smith@email.com | +1-555-0100 | London, UK\n\n"
            "EXPERIENCE\n"
            "Senior Software Engineer – Acme Corp (2018–2024)\n"
            "Led backend services team. Built REST APIs with Python and FastAPI.\n\n"
            "SKILLS\nPython, FastAPI, Docker, PostgreSQL, AWS\n\n"
            "EDUCATION\nBSc Computer Science, University of London, 2015"
        ),
        "expected": {
            "seniority": "Senior",
            "technologies_used": ["Python", "FastAPI", "Docker", "PostgreSQL", "AWS"],
            "years_of_experience": 6,
        },
    },
    {
        "cv_text": (
            "Carlos Mendez\n"
            "carlos@dev.io | Madrid, Spain\n\n"
            "Junior Frontend Developer with 1 year of experience.\n"
            "Skills: React, TypeScript, HTML, CSS\n\n"
            "Education: Bachelor in Software Engineering, Universidad Complutense, 2022"
        ),
        "expected": {
            "seniority": "Junior",
            "technologies_used": ["React", "TypeScript"],
            "years_of_experience": 1,
        },
    },
    {
        "cv_text": (
            "Dr. Priya Nair\n"
            "priya.nair@ml.org | Bangalore, India\n\n"
            "Lead Machine Learning Engineer | 9 years in production ML systems.\n"
            "Expertise: PyTorch, TensorFlow, Python, Spark, Airflow, GCP, Kubernetes.\n"
            "PhD in Computer Science (NLP), IIT Bombay, 2014."
        ),
        "expected": {
            "seniority": "Lead",
            "technologies_used": ["PyTorch", "TensorFlow", "Python", "Spark", "GCP"],
            "years_of_experience": 9,
        },
    },
    {
        "cv_text": (
            "Marcus Klein\n"
            "m.klein@fintech.de | Berlin, Germany\n\n"
            "Principal Backend Engineer (10+ years)\n"
            "Specialising in distributed systems, Go, Rust, Kafka, PostgreSQL, Docker.\n"
            "MSc Distributed Systems, TU Berlin, 2012."
        ),
        "expected": {
            "seniority": "Principal",
            "technologies_used": ["Go", "Rust", "PostgreSQL", "Docker"],
            "years_of_experience": 10,
        },
    },
    {
        "cv_text": (
            "Sofia Rossi\nsofia@cloud.it | Milan, Italy\n\n"
            "Senior Cloud Solutions Architect – 7 years experience.\n"
            "Azure, AWS, Kubernetes, Terraform, Python, CI/CD pipelines.\n"
            "BSc Information Technology, Politecnico di Milano."
        ),
        "expected": {
            "seniority": "Senior",
            "technologies_used": ["Azure", "AWS", "Kubernetes", "Python"],
            "years_of_experience": 7,
        },
    },
    {
        "cv_text": (
            "Alex Johnson\nalex.j@startup.com | New York, USA\n\n"
            "Mid-level Full Stack Developer, 3 years exp.\n"
            "Node.js, React, MongoDB, TypeScript, Docker.\n"
            "BSc Computer Engineering."
        ),
        "expected": {
            "seniority": "Mid",
            "technologies_used": ["Node.js", "React", "MongoDB", "TypeScript", "Docker"],
            "years_of_experience": 3,
        },
    },
    {
        "cv_text": (
            "Li Wei\nli.wei@data.cn | Shanghai, China\n\n"
            "Senior Data Engineer | 5 years at scale.\n"
            "Apache Spark, Airflow, Python, SQL, AWS Glue, Redshift.\n"
            "Master of Engineering, Tsinghua University, 2018."
        ),
        "expected": {
            "seniority": "Senior",
            "technologies_used": ["Spark", "Airflow", "Python", "SQL", "AWS"],
            "years_of_experience": 5,
        },
    },
    {
        "cv_text": (
            "Emma Larsson\nemma@devops.se | Stockholm, Sweden\n\n"
            "DevOps Engineer (Mid-level) – 4 years.\n"
            "Kubernetes, Docker, Terraform, CI/CD, Python, Linux.\n"
            "Bachelor in System Administration."
        ),
        "expected": {
            "seniority": "Mid",
            "technologies_used": ["Kubernetes", "Docker", "Python", "Linux"],
            "years_of_experience": 4,
        },
    },
    {
        "cv_text": (
            "Tomás García\ntomas@backend.mx | Mexico City, Mexico\n\n"
            "Intern Software Developer – currently studying.\n"
            "Learning Python, Django, Git, SQL.\n"
            "BSc Computer Science, UNAM (in progress)."
        ),
        "expected": {
            "seniority": "Intern",
            "technologies_used": ["Python", "Django", "SQL"],
            "years_of_experience": 0,
        },
    },
    {
        "cv_text": (
            "Anya Petrov\nanya.petrov@security.ru | Prague, Czech Republic\n\n"
            "Senior Security Engineer | 8 years in cyber security.\n"
            "Python, Linux, AWS, Penetration Testing, SIEM, Compliance.\n"
            "MSc Information Security."
        ),
        "expected": {
            "seniority": "Senior",
            "technologies_used": ["Python", "Linux", "AWS"],
            "years_of_experience": 8,
        },
    },
]


GOLDEN_MATCHES = [
    {
        "description": "Python/AWS backend role — candidate with Python+AWS should win",
        "requirement": {
            "id": "req_eval_01",
            "title": "Backend Engineer",
            "must_have": ["Python", "AWS", "FastAPI"],
            "nice_to_have": ["Docker"],
            "location": None,
        },
        "candidates": [
            {"id": "c1", "seniority": "Senior", "skills": ["Python", "AWS", "FastAPI", "Docker"], "experience": 6, "location": None},
            {"id": "c2", "seniority": "Junior", "skills": ["JavaScript", "React"], "experience": 1, "location": None},
            {"id": "c3", "seniority": "Mid", "skills": ["Python", "Django"], "experience": 3, "location": None},
        ],
        "expected_winner_index": 0,
    },
    {
        "description": "ML Engineer role — PyTorch + TensorFlow candidate should win",
        "requirement": {
            "id": "req_eval_02",
            "title": "Machine Learning Engineer",
            "must_have": ["PyTorch", "TensorFlow", "Python"],
            "nice_to_have": ["Spark"],
            "location": None,
        },
        "candidates": [
            {"id": "c1", "seniority": "Junior", "skills": ["Python", "SQL"], "experience": 1, "location": None},
            {"id": "c2", "seniority": "Lead", "skills": ["PyTorch", "TensorFlow", "Python", "Spark"], "experience": 9, "location": None},
            {"id": "c3", "seniority": "Mid", "skills": ["Python", "Airflow"], "experience": 4, "location": None},
        ],
        "expected_winner_index": 1,
    },
    {
        "description": "DevOps role — Kubernetes + Docker + Terraform candidate should win",
        "requirement": {
            "id": "req_eval_03",
            "title": "DevOps Engineer",
            "must_have": ["Kubernetes", "Docker", "Terraform"],
            "nice_to_have": ["Python", "Linux"],
            "location": None,
        },
        "candidates": [
            {"id": "c1", "seniority": "Senior", "skills": ["Kubernetes", "Docker", "Terraform", "Python", "Linux"], "experience": 7, "location": None},
            {"id": "c2", "seniority": "Junior", "skills": ["Docker", "Git"], "experience": 1, "location": None},
            {"id": "c3", "seniority": "Mid", "skills": ["AWS", "Python"], "experience": 4, "location": None},
        ],
        "expected_winner_index": 0,
    },
    {
        "description": "Full stack role — Node + React wins over Go backend specialist",
        "requirement": {
            "id": "req_eval_04",
            "title": "Full Stack Developer",
            "must_have": ["Node.js", "React", "TypeScript"],
            "nice_to_have": ["MongoDB"],
            "location": None,
        },
        "candidates": [
            {"id": "c1", "seniority": "Mid", "skills": ["Go", "PostgreSQL"], "experience": 5, "location": None},
            {"id": "c2", "seniority": "Mid", "skills": ["Node.js", "React", "TypeScript", "MongoDB"], "experience": 3, "location": None},
            {"id": "c3", "seniority": "Intern", "skills": ["HTML", "CSS", "JavaScript"], "experience": 0, "location": None},
        ],
        "expected_winner_index": 1,
    },
    {
        "description": "Data Engineer role — Spark + Airflow candidate wins",
        "requirement": {
            "id": "req_eval_05",
            "title": "Data Engineer",
            "must_have": ["Spark", "Airflow", "Python"],
            "nice_to_have": ["SQL", "AWS"],
            "location": None,
        },
        "candidates": [
            {"id": "c1", "seniority": "Senior", "skills": ["Spark", "Airflow", "Python", "SQL", "AWS"], "experience": 5, "location": None},
            {"id": "c2", "seniority": "Mid", "skills": ["Python", "Django", "PostgreSQL"], "experience": 3, "location": None},
        ],
        "expected_winner_index": 0,
    },
    {
        "description": "Cloud Architect — Azure + AWS heavy candidate wins",
        "requirement": {
            "id": "req_eval_06",
            "title": "Cloud Solutions Architect",
            "must_have": ["Azure", "AWS", "Kubernetes"],
            "nice_to_have": ["Python", "Terraform"],
            "location": None,
        },
        "candidates": [
            {"id": "c1", "seniority": "Junior", "skills": ["Python", "Git"], "experience": 1, "location": None},
            {"id": "c2", "seniority": "Senior", "skills": ["Azure", "AWS", "Kubernetes", "Python", "Terraform"], "experience": 7, "location": None},
            {"id": "c3", "seniority": "Mid", "skills": ["AWS", "Docker"], "experience": 4, "location": None},
        ],
        "expected_winner_index": 1,
    },
    {
        "description": "Security Engineer — Python+AWS+Linux wins",
        "requirement": {
            "id": "req_eval_07",
            "title": "Security Engineer",
            "must_have": ["Python", "Linux", "AWS"],
            "nice_to_have": [],
            "location": None,
        },
        "candidates": [
            {"id": "c1", "seniority": "Senior", "skills": ["Python", "Linux", "AWS"], "experience": 8, "location": None},
            {"id": "c2", "seniority": "Junior", "skills": ["Python", "SQL"], "experience": 1, "location": None},
        ],
        "expected_winner_index": 0,
    },
    {
        "description": "Go backend — Go+Rust+PostgreSQL wins over Python-only",
        "requirement": {
            "id": "req_eval_08",
            "title": "Principal Backend Engineer",
            "must_have": ["Go", "PostgreSQL"],
            "nice_to_have": ["Rust", "Docker"],
            "location": None,
        },
        "candidates": [
            {"id": "c1", "seniority": "Principal", "skills": ["Go", "Rust", "PostgreSQL", "Docker"], "experience": 10, "location": None},
            {"id": "c2", "seniority": "Senior", "skills": ["Python", "FastAPI", "PostgreSQL"], "experience": 6, "location": None},
        ],
        "expected_winner_index": 0,
    },
    {
        "description": "React frontend — React+TypeScript wins over Vue candidate",
        "requirement": {
            "id": "req_eval_09",
            "title": "Frontend Developer",
            "must_have": ["React", "TypeScript"],
            "nice_to_have": ["Node.js"],
            "location": None,
        },
        "candidates": [
            {"id": "c1", "seniority": "Mid", "skills": ["Vue", "JavaScript"], "experience": 3, "location": None},
            {"id": "c2", "seniority": "Senior", "skills": ["React", "TypeScript", "Node.js"], "experience": 5, "location": None},
        ],
        "expected_winner_index": 1,
    },
    {
        "description": "Intern Python role — intern with Python+Django beats senior Go specialist",
        "requirement": {
            "id": "req_eval_10",
            "title": "Python Intern",
            "must_have": ["Python", "Django"],
            "nice_to_have": ["SQL"],
            "location": None,
        },
        "candidates": [
            {"id": "c1", "seniority": "Intern", "skills": ["Python", "Django", "SQL"], "experience": 0, "location": None},
            {"id": "c2", "seniority": "Senior", "skills": ["Go", "PostgreSQL", "Rust"], "experience": 10, "location": None},
        ],
        "expected_winner_index": 0,
    },
]
