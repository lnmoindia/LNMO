import { useAuth } from "../../context/AuthContext";
import { NotPermitted } from "../../pages/StatusPages";

// Renders children only for a true institution_admin. Principals (elevated teachers) and anyone else
// get a friendly "not permitted" panel — mirrors the server-side exclusions so direct URLs never crash.
export const AdminOnly = ({ children }) => {
  const { user } = useAuth();
  return user?.role === "institution_admin" ? children : <NotPermitted />;
};

// Admin OR an elevated principal (unit-scoped access is enforced server-side on every call).
export const AdminOrPrincipal = ({ children }) => {
  const { user } = useAuth();
  return (user?.role === "institution_admin" || user?.is_principal) ? children : <NotPermitted />;
};
