import { useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Loading } from "../components/ui";

export default function AuthCallback() { const { session, completeOidc } = useAuth(); const once = useRef(false); const [error, setError] = useState(""); useEffect(() => { if (!once.current) { once.current = true; completeOidc().catch((reason) => setError(reason instanceof Error ? reason.message : "Sign-in failed.")); } }, [completeOidc]); if (session) return <Navigate to="/" replace/>; return <main className="center-page">{error ? <div className="error-notice">{error}</div> : <Loading/>}</main>; }
