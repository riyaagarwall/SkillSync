-- Sample data (all names are fictional)

INSERT INTO employees (name, email, role, experience_years, hourly_cost) VALUES
('Aarav Mehta',  'aarav@example.com',  'employee', 5.0, 40),
('Diya Sharma',  'diya@example.com',   'employee', 3.5, 30),
('Rohan Iyer',   'rohan@example.com',  'employee', 7.0, 55),
('Ananya Rao',   'ananya@example.com', 'employee', 2.0, 20),
('Kabir Singh',  'kabir@example.com',  'employee', 4.5, 38),
('Meera Nair',   'meera@example.com',  'employee', 6.0, 50),
('Vikram Joshi', 'vikram@example.com', 'employee', 1.0, 15),
('Isha Verma',   'isha@example.com',   'employee', 8.0, 65),
('Neha Kapoor',  'neha@example.com',   'pm',       10.0, 80),
('Arjun Das',    'arjun@example.com',  'employee', 3.0, 28);

INSERT INTO skills (name) VALUES
('Python'), ('SQL'), ('JavaScript'), ('React'),
('Flask'), ('Machine Learning'), ('Data Visualization'), ('Docker');

-- employee_id, skill_id, proficiency (0 to 5)
INSERT INTO employee_skills (employee_id, skill_id, proficiency) VALUES
(1,1,4),(1,2,3),(1,5,4),(1,8,2),
(2,1,3),(2,2,4),(2,7,4),(2,6,2),
(3,1,5),(3,6,5),(3,2,4),(3,8,3),
(4,3,3),(4,4,3),(4,1,2),
(5,3,4),(5,4,4),(5,5,2),(5,8,3),
(6,1,4),(6,2,5),(6,7,5),
(7,1,2),(7,2,2),(7,3,2),
(8,1,5),(8,5,5),(8,8,4),(8,2,4),(8,6,3),
(9,2,3),(9,7,3),
(10,4,4),(10,3,4),(10,7,3);

INSERT INTO certifications (employee_id, name, issued_on) VALUES
(3, 'AWS Certified Machine Learning - Specialty', '2025-06-15'),
(8, 'AWS Certified Developer - Associate',        '2024-09-10'),
(6, 'Microsoft Power BI Data Analyst',            '2025-03-20'),
(2, 'Google Data Analytics Certificate',          '2024-12-05'),
(1, 'Python Institute PCAP',                      '2025-01-18'),
(5, 'Meta Front-End Developer Certificate',       '2025-08-02');

INSERT INTO projects (name, start_date, end_date, headcount, min_experience_years, billing_rate) VALUES
('Retail Analytics Platform', '2026-11-01', '2027-03-31', 3, 3.0, 120),
('Customer Support Chatbot',  '2026-11-15', '2027-02-28', 2, 4.0, 150);

-- project_id, skill_id, min_proficiency
INSERT INTO project_requirements (project_id, skill_id, min_proficiency) VALUES
(1,1,3),(1,2,3),(1,7,3),
(2,1,4),(2,6,3);

-- Isha is fully booked (100%), Rohan is 60% booked on project 1
INSERT INTO allocations (employee_id, project_id, start_date, end_date, percent_allocated) VALUES
(8, 1, '2026-11-01', '2027-03-31', 100),
(3, 1, '2026-11-01', '2027-03-31', 60);

INSERT INTO timesheets (allocation_id, week_start, hours, status) VALUES
(1, '2026-11-02', 40, 'approved'),
(2, '2026-11-02', 24, 'pending');