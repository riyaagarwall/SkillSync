CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'employee'
        CHECK (role IN ('employee', 'pm', 'admin')),
    experience_years NUMERIC(3,1) NOT NULL DEFAULT 0
        CHECK (experience_years >= 0),
    hourly_cost NUMERIC(8,2) NOT NULL DEFAULT 0
);

CREATE TABLE skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(80) UNIQUE NOT NULL
);

CREATE TABLE employee_skills (
    employee_id INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    skill_id INT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    proficiency INT NOT NULL CHECK (proficiency BETWEEN 0 AND 5),
    PRIMARY KEY (employee_id, skill_id)
);

CREATE TABLE certifications (
    id SERIAL PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    issued_on DATE
);

CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    headcount INT NOT NULL CHECK (headcount > 0),
    min_experience_years NUMERIC(3,1) NOT NULL DEFAULT 0,
    billing_rate NUMERIC(8,2) NOT NULL DEFAULT 0,
    CHECK (end_date >= start_date)
);

CREATE TABLE project_requirements (
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    skill_id INT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    min_proficiency INT NOT NULL CHECK (min_proficiency BETWEEN 1 AND 5),
    PRIMARY KEY (project_id, skill_id)
);

CREATE TABLE allocations (
    id SERIAL PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES employees(id),
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    percent_allocated INT NOT NULL CHECK (percent_allocated BETWEEN 1 AND 100),
    CHECK (end_date >= start_date)
);

CREATE TABLE timesheets (
    id SERIAL PRIMARY KEY,
    allocation_id INT NOT NULL REFERENCES allocations(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    hours NUMERIC(4,1) NOT NULL CHECK (hours >= 0 AND hours <= 80),
    status VARCHAR(10) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by INT REFERENCES employees(id),
    reviewed_at TIMESTAMPTZ,
    UNIQUE (allocation_id, week_start)
);