CREATE TABLE IF NOT EXISTS stores (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    address VARCHAR(255),
    phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS classrooms (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 20,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    real_name VARCHAR(50),
    role VARCHAR(20) NOT NULL DEFAULT 'admin',
    store_id INTEGER REFERENCES stores(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
    id SERIAL PRIMARY KEY,
    course_code VARCHAR(50) UNIQUE NOT NULL,
    course_name VARCHAR(100) NOT NULL,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    classroom_id INTEGER NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    max_students INTEGER NOT NULL DEFAULT 20,
    waitlist_count INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    freeze_time TIMESTAMP NOT NULL,
    instructor VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_courses_start_time ON courses(start_time);
CREATE INDEX IF NOT EXISTS idx_courses_status ON courses(status);

CREATE TABLE IF NOT EXISTS registrations (
    id SERIAL PRIMARY KEY,
    reg_code VARCHAR(50) UNIQUE NOT NULL,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    member_name VARCHAR(100) NOT NULL,
    member_phone VARCHAR(20) NOT NULL,
    registration_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checkin_time TIMESTAMP,
    dropout_time TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'registered',
    is_waitlist BOOLEAN NOT NULL DEFAULT FALSE,
    waitlist_order INTEGER,
    promoted_from_waitlist BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_registrations_course_id ON registrations(course_id);
CREATE INDEX IF NOT EXISTS idx_registrations_member_phone ON registrations(member_phone);
CREATE INDEX IF NOT EXISTS idx_registrations_status ON registrations(status);

CREATE TABLE IF NOT EXISTS waitlist_history (
    id SERIAL PRIMARY KEY,
    registration_id INTEGER NOT NULL REFERENCES registrations(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    action_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    old_waitlist_order INTEGER,
    new_waitlist_order INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS blacklist (
    id SERIAL PRIMARY KEY,
    member_phone VARCHAR(20) NOT NULL,
    member_name VARCHAR(100),
    reason TEXT NOT NULL,
    start_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    is_auto BOOLEAN NOT NULL DEFAULT FALSE,
    no_show_count INTEGER DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_blacklist_member_phone ON blacklist(member_phone);
CREATE INDEX IF NOT EXISTS idx_blacklist_status ON blacklist(status);

CREATE TABLE IF NOT EXISTS member_packages (
    id SERIAL PRIMARY KEY,
    package_code VARCHAR(50) UNIQUE NOT NULL,
    member_phone VARCHAR(20) NOT NULL,
    member_name VARCHAR(100),
    package_name VARCHAR(100) NOT NULL,
    package_type VARCHAR(20) NOT NULL,
    store_id INTEGER REFERENCES stores(id) ON DELETE SET NULL,
    total_count INTEGER NOT NULL DEFAULT 0,
    remaining_count INTEGER NOT NULL DEFAULT 0,
    reserved_count INTEGER NOT NULL DEFAULT 0,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_member_packages_member_phone ON member_packages(member_phone);
CREATE INDEX IF NOT EXISTS idx_member_packages_status ON member_packages(status);
CREATE INDEX IF NOT EXISTS idx_member_packages_end_time ON member_packages(end_time);

CREATE TABLE IF NOT EXISTS course_deductions (
    id SERIAL PRIMARY KEY,
    registration_id INTEGER NOT NULL REFERENCES registrations(id) ON DELETE CASCADE,
    package_id INTEGER NOT NULL REFERENCES member_packages(id) ON DELETE CASCADE,
    deduction_type VARCHAR(20) NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_course_deductions_registration_id ON course_deductions(registration_id);
CREATE INDEX IF NOT EXISTS idx_course_deductions_package_id ON course_deductions(package_id);

CREATE TABLE IF NOT EXISTS system_config (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO system_config (key, value, description) VALUES
    ('no_show_threshold', '3', '失约次数达到该阈值自动加入限制名单')
ON CONFLICT DO NOTHING;

INSERT INTO stores (name, address, phone) VALUES
    ('总店', '北京市朝阳区健身路1号', '010-12345678'),
    ('分店A', '北京市海淀区运动街88号', '010-87654321')
ON CONFLICT DO NOTHING;

INSERT INTO classrooms (store_id, name, capacity, description) VALUES
    (1, '一号教室', 25, '团课教室，配备专业音响设备'),
    (1, '二号教室', 30, '瑜伽专用教室'),
    (2, '一号教室', 20, '动感单车教室')
ON CONFLICT DO NOTHING;

INSERT INTO users (username, password_hash, real_name, role, store_id) VALUES
    ('admin', 'pbkdf2:sha256:260000$4b8a1a0f8b4cf5f8$16341e710f2eb998c4e1d6506c9877ed906af3d5f469f2d770953b4c2ff83dbf', '系统管理员', 'admin', NULL)
ON CONFLICT DO NOTHING;
