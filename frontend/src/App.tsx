import { useEffect, useState } from "react";

type Health = { status: string; message: string };

export default function App() {
  const [data, setData] = useState<Health | null>(null);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/health/")
      .then((res) => res.json())
      .then(setData)
      .catch(console.error);
  }, []);

  return (
    <div style={{ padding: 24 }}>
      <h1>Career AI</h1>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}