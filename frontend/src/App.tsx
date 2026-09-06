import { NavLink, Route, Routes } from "react-router-dom";
import Mascot from "./components/Mascot";
import UserSwitcher from "./components/UserSwitcher";
import AskPage from "./pages/AskPage";
import DocumentDetailPage from "./pages/DocumentDetailPage";
import DocumentsPage from "./pages/DocumentsPage";

export default function App() {
  return (
    <>
      <nav className="top">
        <span className="brand">AtlasDocs</span>
        <Mascot
          size={38}
          static
          tip="A multi-tenant RAG app: upload documents, ask questions, get answers grounded in your own files"
        />
        <NavLink
          to="/documents"
          className={({ isActive }) => (isActive ? "active" : "")}
          style={{ marginLeft: "auto" }}
        >
          Documents
        </NavLink>
        <NavLink to="/ask" className={({ isActive }) => (isActive ? "active" : "")}>
          Ask
        </NavLink>
        <UserSwitcher />
      </nav>
      <div className="app">
        <Routes>
          <Route path="/" element={<DocumentsPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/documents/:id" element={<DocumentDetailPage />} />
          <Route path="/ask" element={<AskPage />} />
        </Routes>
      </div>
    </>
  );
}
