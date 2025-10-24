export default function Home() {
  const api = process.env.NEXT_PUBLIC_API_BASE!;
  return (
    <main className="min-h-screen flex items-center justify-center">
      <div className="p-8 rounded-2xl shadow max-w-lg text-center space-y-6">
        <h1 className="text-3xl font-bold">Inbox Summarizer</h1>
        <p className="text-gray-600">Sign in with Google and get concise summaries of your most important emails.</p>
        <a
          href={`${api}/auth/google/login`}
          className="inline-block px-4 py-2 rounded-xl bg-black text-white"
        >
          Continue with Google
        </a>
      </div>
    </main>
  );
}
