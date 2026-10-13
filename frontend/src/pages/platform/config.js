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

export const institutionsConfig = {
  title: "Institutions",
  singular: "Institution",
  description: "Schools and campuses provisioned on the platform.",
  endpoint: "res/institutions",
  columns: [
    { key: "name", label: "Name" },
    { key: "code", label: "Code" },
    { key: "domain", label: "Domain" },
    { key: "city", label: "City" },
    { key: "status", label: "Status", render: statusPill },
  ],
  fields: [
    { name: "name", label: "Institution name", required: true },
    { name: "code", label: "Code" },
    { name: "domain", label: "Domain (e.g. greenwood.edu)" },
    { name: "city", label: "City" },
    { name: "contact_email", label: "Contact email", type: "email" },
    { name: "phone", label: "Phone" },
    statusField,
    { name: "admin_name", label: "Admin name", createOnly: true },
    { name: "admin_email", label: "Admin login email", type: "email", createOnly: true },
    { name: "admin_password", label: "Admin password", type: "password", createOnly: true },
  ],
};

export const plansConfig = {
  title: "Plans",
  singular: "Plan",
  description: "Subscription plans and entitlements offered to institutions.",
  endpoint: "res/plans",
  columns: [
    { key: "name", label: "Name" },
    { key: "code", label: "Code" },
    { key: "price_monthly", label: "Monthly Price" },
    { key: "max_students", label: "Max Students" },
    { key: "status", label: "Status", render: statusPill },
  ],
  fields: [
    { name: "name", label: "Plan name", required: true },
    { name: "code", label: "Code" },
    { name: "price_monthly", label: "Monthly price", type: "number" },
    { name: "max_students", label: "Max students", type: "number" },
    { name: "description", label: "Description", type: "textarea" },
    statusField,
  ],
};
