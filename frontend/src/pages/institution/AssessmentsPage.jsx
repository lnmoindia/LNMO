import { useNavigate } from "react-router-dom";
import { PenSquare } from "lucide-react";
import ResourcePage from "../../components/common/ResourcePage";
import { assessmentsConfig } from "./config";

export default function AssessmentsPage() {
  const navigate = useNavigate();
  return (
    <ResourcePage
      {...assessmentsConfig}
      rowActions={[{ title: "Enter marks", icon: PenSquare, testId: "marks-btn", onClick: (row) => navigate(`/app/assessments/${row.id}/marks`) }]}
    />
  );
}
