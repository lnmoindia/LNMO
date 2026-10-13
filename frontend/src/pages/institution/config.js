const roleBadge = (row) => {
  const map = {
    institution_admin: "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400",
    teacher: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
    student: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400",
    staff: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
    platform_admin: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${map[row.role] || map.staff}`}>
      {(row.role || "").replace("_", " ")}
    </span>
  );
};

const statusPill = (row) => (
  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
    (row.status || "active") === "active"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
      : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
  }`}>{row.status || "active"}</span>
);

const statusField = {
  name: "status", label: "Status", type: "select", default: "active",
  options: [{ value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }],
};

const fullName = (row) => `${row.first_name || ""} ${row.last_name || ""}`.trim() || "—";

const SUBJECT_TYPE_LABELS = { core: "Core", elective: "Elective", language: "Language", practical: "Practical / Lab" };
const subjectType = (row) => {
  const t = (row.type || "").toString().trim();
  if (!t) return "Core";
  return SUBJECT_TYPE_LABELS[t.toLowerCase()] || t;
};

export const studentsConfig = {
  title: "Students",
  singular: "Student",
  description: "Admitted students of your institution.",
  endpoint: "res/students",
  columns: [
    { key: "name", label: "Name", render: fullName },
    { key: "admission_no", label: "Admission No." },
    { key: "class_name", label: "Class" },
    { key: "section", label: "Section" },
    { key: "guardian_name", label: "Guardian" },
    { key: "status", label: "Status", render: statusPill },
  ],
  fields: [
    { name: "first_name", label: "First name", required: true },
    { name: "last_name", label: "Last name" },
    { name: "admission_no", label: "Admission number" },
    { name: "class_name", label: "Class" },
    { name: "section", label: "Section" },
    { name: "email", label: "Email", type: "email" },
    { name: "guardian_name", label: "Guardian name" },
    { name: "guardian_phone", label: "Guardian phone" },
    { name: "date_of_birth", label: "Date of birth", type: "date" },
    statusField,
  ],
};

export const teachersConfig = {
  title: "Teachers",
  singular: "Teacher",
  description: "Teaching staff of your institution.",
  endpoint: "res/teachers",
  columns: [
    { key: "name", label: "Name", render: fullName },
    { key: "employee_id", label: "Employee ID" },
    { key: "email", label: "Email" },
    { key: "specialization", label: "Specialization" },
    { key: "phone", label: "Phone" },
    { key: "status", label: "Status", render: statusPill },
  ],
  fields: [
    { name: "first_name", label: "First name", required: true },
    { name: "last_name", label: "Last name" },
    { name: "employee_id", label: "Employee ID" },
    { name: "email", label: "Email", type: "email" },
    { name: "phone", label: "Phone" },
    { name: "specialization", label: "Specialization" },
    statusField,
  ],
};

export const usersConfig = {
  title: "Users",
  singular: "User",
  description: "Login accounts with access to this institution.",
  endpoint: "users",
  columns: [
    { key: "name", label: "Name" },
    { key: "email", label: "Email" },
    { key: "role", label: "Role", render: roleBadge },
    { key: "phone", label: "Phone" },
    { key: "status", label: "Status", render: statusPill },
  ],
  fields: [
    { name: "name", label: "Full name", required: true },
    { name: "email", label: "Login email", type: "email", required: true, createOnly: true },
    { name: "password", label: "Password", type: "password" },
    {
      name: "role", label: "Role", type: "select", required: true,
      options: [
        { value: "institution_admin", label: "Institution Admin" },
        { value: "teacher", label: "Teacher" },
        { value: "student", label: "Student" },
        { value: "staff", label: "Staff" },
      ],
    },
    { name: "phone", label: "Phone" },
    statusField,
  ],
};

export const classesConfig = {
  title: "Classes",
  singular: "Class",
  description: "Grade levels offered by your institution.",
  endpoint: "res/classes",
  columns: [
    { key: "name", label: "Name" },
    { key: "academic_unit_name", label: "Academic Unit" },
    { key: "grade_level", label: "Grade Level" },
    { key: "class_teacher", label: "Class Teacher" },
    { key: "status", label: "Status", render: statusPill },
  ],
  fields: [
    { name: "name", label: "Class name", required: true },
    { name: "academic_unit_id", label: "Academic unit", optionsUrl: "lookup/academic_units", required: true },
    { name: "grade_level", label: "Grade level" },
    { name: "class_teacher", label: "Class teacher" },
    statusField,
  ],
};

export const sectionsConfig = {
  title: "Sections",
  singular: "Section",
  description: "Sections within classes.",
  endpoint: "res/sections",
  columns: [
    { key: "name", label: "Section" },
    { key: "class_name", label: "Class" },
    { key: "capacity", label: "Capacity" },
    { key: "room", label: "Room" },
    { key: "status", label: "Status", render: statusPill },
  ],
  fields: [
    { name: "name", label: "Section name", required: true },
    { name: "class_name", label: "Class" },
    { name: "capacity", label: "Capacity", type: "number" },
    { name: "room", label: "Room" },
    statusField,
  ],
};

export const noticesConfig = {
  title: "Notices",
  singular: "Notice",
  description: "Circulars and announcements shown on teacher and student dashboards.",
  endpoint: "res/notices",
  fields: [
    { name: "title", label: "Title", required: true },
    { name: "body", label: "Message", type: "textarea" },
    {
      name: "audience", label: "Audience", type: "select", default: "all",
      options: [
        { value: "all", label: "Everyone" },
        { value: "teachers", label: "Teachers only" },
        { value: "students", label: "Students only" },
      ],
    },
    {
      name: "status", label: "Status", type: "select", default: "published",
      options: [
        { value: "published", label: "Published" },
        { value: "draft", label: "Draft" },
      ],
    },
  ],
  columns: [
    { key: "title", label: "Title" },
    { key: "audience", label: "Audience", render: (r) => ({ all: "Everyone", teachers: "Teachers", students: "Students" }[r.audience] || "Everyone") },
    { key: "status", label: "Status" },
    { key: "author_name", label: "Posted by" },
    { key: "created_at", label: "Posted", render: (r) => (r.created_at || "").slice(0, 10) },
  ],
};

export const subjectsConfig = {
  title: "Subjects",
  singular: "Subject",
  description: "Your institution's subject catalog. Class-level marks & lab config live on Subject Offerings (Class Hub).",
  endpoint: "res/subjects",
  columns: [
    { key: "name", label: "Name" },
    { key: "code", label: "Code" },
    { key: "type", label: "Type", render: subjectType },
    { key: "default_max_marks", label: "Default max", render: (r) => r.default_max_marks || 100 },
    { key: "status", label: "Status", render: statusPill },
  ],
  fields: [
    { name: "name", label: "Subject name", required: true },
    { name: "code", label: "Code (auto-generated if blank)" },
    {
      name: "type", label: "Type", type: "select", default: "core",
      options: [
        { value: "core", label: "Core" },
        { value: "elective", label: "Elective" },
        { value: "language", label: "Language" },
        { value: "practical", label: "Practical / Lab" },
      ],
    },
    { name: "default_max_marks", label: "Default max marks", type: "number", default: 100 },
    statusField,
  ],
};

export const academicUnitsConfig = {
  title: "Academic Units",
  singular: "Academic Unit",
  description: "Structural bands (e.g. Lower Primary, High School) that classes belong to.",
  endpoint: "res/academic_units",
  columns: [
    { key: "name", label: "Name" },
    { key: "code", label: "Code" },
    { key: "attendance_model", label: "Attendance" },
    { key: "assessment_model", label: "Assessment" },
    { key: "grading_model", label: "Grading" },
    { key: "status", label: "Status", render: statusPill },
  ],
  fields: [
    { name: "name", label: "Unit name", required: true },
    { name: "code", label: "Code" },
    { name: "sort_order", label: "Sort order", type: "number" },
    { name: "attendance_model", label: "Attendance model", type: "select", default: "daily",
      options: [{ value: "daily", label: "Daily" }, { value: "period", label: "Period-wise" }, { value: "none", label: "None" }] },
    { name: "subject_model", label: "Subject model", type: "select", default: "fixed",
      options: [{ value: "fixed", label: "Fixed" }, { value: "elective", label: "Elective" }, { value: "stream", label: "Stream" }] },
    { name: "assessment_model", label: "Assessment model", type: "select", default: "marks",
      options: [{ value: "marks", label: "Marks" }, { value: "grades", label: "Grades" }, { value: "none", label: "None" }] },
    { name: "grading_model", label: "Grading model", type: "select", default: "percentage",
      options: [{ value: "percentage", label: "Percentage" }, { value: "letter", label: "Letter" }, { value: "gpa", label: "GPA" }] },
    statusField,
  ],
};

export const academicYearsConfig = {
  title: "Academic Years",
  singular: "Academic Year",
  description: "Academic sessions used for enrollments and reporting.",
  endpoint: "res/academic_years",
  columns: [
    { key: "name", label: "Name" },
    { key: "start_date", label: "Start Date" },
    { key: "end_date", label: "End Date" },
    {
      key: "status", label: "Status",
      render: (row) => (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
          (row.status || "active") === "active"
            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
            : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
        }`}>{row.status || "active"}</span>
      ),
    },
  ],
  fields: [
    { name: "name", label: "Name (e.g. 2026–27)", required: true },
    { name: "start_date", label: "Start date", type: "date" },
    { name: "end_date", label: "End date", type: "date" },
    {
      name: "status", label: "Status", type: "select", default: "active",
      options: [{ value: "active", label: "Active" }, { value: "closed", label: "Closed" }],
    },
  ],
};

export const enrollmentsConfig = {
  title: "Enrollments",
  singular: "Enrollment",
  description: "Place students into classes and sections for an academic year.",
  endpoint: "res/enrollments",
  columns: [
    { key: "student_name", label: "Student" },
    { key: "admission_no", label: "Admission No." },
    { key: "academic_year", label: "Academic Year" },
    { key: "class_name", label: "Class" },
    { key: "section", label: "Section" },
  ],
  fields: [
    { name: "student_id", label: "Student", optionsUrl: "lookup/students", required: true },
    { name: "academic_year", label: "Academic year", optionsUrl: "lookup/academic_years" },
    { name: "class_name", label: "Class", optionsUrl: "lookup/classes" },
    { name: "section", label: "Section", optionsUrl: "lookup/sections" },
  ],
};

export const teacherAssignmentsConfig = {
  title: "Teacher Assignments",
  singular: "Teacher Assignment",
  description: "Assign teacher accounts to classes, sections and subjects.",
  endpoint: "res/teacher_assignments",
  columns: [
    { key: "teacher_name", label: "Teacher" },
    { key: "teacher_email", label: "Email" },
    { key: "class_name", label: "Class" },
    { key: "section", label: "Section" },
    { key: "subject", label: "Subject" },
  ],
  fields: [
    { name: "teacher_email", label: "Teacher (login account)", optionsUrl: "lookup/teacher_users", required: true },
    { name: "class_name", label: "Class", optionsUrl: "lookup/classes" },
    { name: "section", label: "Section", optionsUrl: "lookup/sections" },
    { name: "subject", label: "Subject", optionsUrl: "lookup/subjects" },
  ],
};

export const assessmentsConfig = {
  title: "Assessments",
  singular: "Assessment",
  description: "Exams and tests. Enter marks, then publish results.",
  endpoint: "res/assessments",
  columns: [
    { key: "name", label: "Name" },
    { key: "subject", label: "Subject" },
    { key: "class_name", label: "Class" },
    { key: "section", label: "Section" },
    { key: "max_marks", label: "Max Marks" },
    { key: "date", label: "Date" },
    {
      key: "status", label: "Status",
      render: (row) => (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
          row.status === "published"
            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
            : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400"
        }`}>{row.status || "draft"}</span>
      ),
    },
  ],
  fields: [
    { name: "name", label: "Assessment name", required: true },
    { name: "subject", label: "Subject", optionsUrl: "lookup/subjects" },
    { name: "class_name", label: "Class", optionsUrl: "lookup/classes" },
    { name: "section", label: "Section", optionsUrl: "lookup/sections" },
    { name: "max_marks", label: "Max marks", type: "number" },
    { name: "date", label: "Date", type: "date" },
  ],
};
