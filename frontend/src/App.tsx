import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, Link } from "react-router-dom";
import { api, getAccessToken, setAccessToken } from "./api/client";
import Welcome from "./pages/Welcome";
import Garden from "./pages/Garden";
import WishDetailPage from "./pages/WishDetail";
import Book from "./pages/Book";
import MemoryPage from "./pages/MemoryPage";

/** 匿名建号：没有表单，点开就有一个属于自己的地方（S01 Step 3）。 */
function useAnonymousSpace(): { ready: boolean; failed: boolean; retry: () => void } {
  const [ready, setReady] = useState(() => getAccessToken() !== null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (ready) return;
    let cancelled = false;
    void (async () => {
      try {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai";
        const body = await api<{ access_token: string }>("/auth/anonymous", {
          method: "POST",
          json: { timezone: tz },
        });
        if (cancelled) return;
        setAccessToken(body.access_token);
        setReady(true);
        setFailed(false);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, attempt]);

  return { ready, failed, retry: () => setAttempt((n) => n + 1) };
}

const TABS = [
  { to: "/garden", label: "未发生之地" },
  { to: "/book", label: "已发生之书" },
] as const;

function BottomNav() {
  const { pathname } = useLocation();
  return (
    <nav
      aria-label="主导航"
      className="fixed inset-x-0 bottom-0 border-t border-line bg-paper/95 backdrop-blur"
    >
      <ul className="mx-auto flex max-w-2xl">
        {TABS.map((tab) => {
          const active = pathname.startsWith(tab.to);
          return (
            <li key={tab.to} className="flex-1">
              <Link
                to={tab.to}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-[44px] items-center justify-center py-3 text-[13px] ${
                  active ? "text-clay" : "text-ink-soft"
                }`}
              >
                {tab.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export default function App() {
  const { ready, failed, retry } = useAnonymousSpace();

  if (failed) {
    // EX-3.1：纸色提示条，不是红字错误。用户写的东西还在这台设备上
    return (
      <main className="mx-auto max-w-2xl px-4 py-16">
        <p className="rounded-card bg-card p-5 text-ink-soft shadow-card">
          这里暂时打不开，你写的还在这台设备上。
        </p>
        <button
          type="button"
          onClick={retry}
          className="mt-4 min-h-[44px] rounded-[999px] bg-clay px-6 text-paper"
        >
          再试一次
        </button>
      </main>
    );
  }

  if (!ready) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-16 text-ink-soft" aria-busy="true">
        正在为你打开这个地方…
      </main>
    );
  }

  return (
    <>
      <div className="mx-auto max-w-2xl px-4 pb-24 pt-6">
        <Routes>
          <Route path="/" element={<Navigate to="/welcome" replace />} />
          <Route path="/welcome" element={<Welcome />} />
          <Route path="/garden" element={<Garden />} />
          <Route path="/wish/:wishId" element={<WishDetailPage />} />
          <Route path="/book" element={<Book />} />
          <Route path="/book/:memoryId" element={<MemoryPage />} />
          <Route path="*" element={<Navigate to="/garden" replace />} />
        </Routes>
      </div>
      <BottomNav />
    </>
  );
}
