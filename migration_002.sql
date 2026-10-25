-- Milestones
CREATE TABLE IF NOT EXISTS milestones (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title VARCHAR(150) NOT NULL,
    due_date DATE NOT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'done'))
);

-- Sample milestones (only added if the table is empty)
INSERT INTO milestones (project_id, title, due_date, status)
SELECT * FROM (VALUES
    (1, 'Requirements signed off', DATE '2026-11-15', 'done'),
    (1, 'Data pipeline ready',     DATE '2026-12-20', 'in_progress'),
    (1, 'Dashboard beta',          DATE '2027-02-10', 'pending'),
    (1, 'Go live',                 DATE '2027-03-25', 'pending'),
    (2, 'Chatbot prototype',       DATE '2026-12-10', 'in_progress'),
    (2, 'Pilot with support team', DATE '2027-01-30', 'pending')
) AS v(project_id, title, due_date, status)
WHERE NOT EXISTS (SELECT 1 FROM milestones);

-- Availability on any date (percent booked and percent free per employee)
CREATE OR REPLACE FUNCTION availability_on(as_of DATE)
RETURNS TABLE (emp_id INT, emp_name VARCHAR, booked_percent INT,
               available_percent INT, active_projects INT)
AS $$
    SELECT e.id,
           e.name,
           COALESCE(SUM(a.percent_allocated), 0)::int,
           GREATEST(100 - COALESCE(SUM(a.percent_allocated), 0), 0)::int,
           COUNT(a.id)::int
    FROM employees e
    LEFT JOIN allocations a
           ON a.employee_id = e.id
          AND a.start_date <= as_of
          AND a.end_date >= as_of
    WHERE e.role = 'employee'
    GROUP BY e.id, e.name
    ORDER BY e.name
$$ LANGUAGE sql STABLE;

-- View 1: availability today
CREATE OR REPLACE VIEW v_employee_availability AS
SELECT * FROM availability_on(CURRENT_DATE);

-- View 2: profitability per project (approved timesheets only)
CREATE OR REPLACE VIEW v_project_profitability AS
SELECT x.*,
       x.revenue - x.cost AS profit,
       CASE WHEN x.revenue > 0
            THEN ROUND(100 * (x.revenue - x.cost) / x.revenue, 1) END AS margin_percent
FROM (
    SELECT p.id AS project_id,
           p.name AS project_name,
           p.billing_rate,
           COALESCE(SUM(t.hours), 0) AS approved_hours,
           COALESCE(SUM(t.hours * p.billing_rate), 0) AS revenue,
           COALESCE(SUM(t.hours * e.hourly_cost), 0) AS cost
    FROM projects p
    LEFT JOIN allocations a ON a.project_id = p.id
    LEFT JOIN timesheets t ON t.allocation_id = a.id AND t.status = 'approved'
    LEFT JOIN employees e ON e.id = a.employee_id
    GROUP BY p.id
) x;

-- View 3: milestone progress per project
CREATE OR REPLACE VIEW v_project_progress AS
SELECT p.id AS project_id,
       p.name AS project_name,
       COUNT(m.id)::int AS total_milestones,
       (COUNT(m.id) FILTER (WHERE m.status = 'done'))::int AS done_milestones,
       (COUNT(m.id) FILTER (WHERE m.status <> 'done'
                              AND m.due_date < CURRENT_DATE))::int AS overdue_milestones,
       CASE WHEN COUNT(m.id) = 0 THEN 0
            ELSE ROUND(100.0 * COUNT(m.id) FILTER (WHERE m.status = 'done') / COUNT(m.id))
       END::int AS percent_complete
FROM projects p
LEFT JOIN milestones m ON m.project_id = p.id
GROUP BY p.id;