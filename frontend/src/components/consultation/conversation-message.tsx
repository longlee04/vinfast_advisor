export function ConversationMessage({ children, role }: Readonly<{ children: React.ReactNode; role: "assistant" | "user" }>) {
  return <div className={`conversation-message message-${role}`} suppressHydrationWarning><span className="message-avatar">{role === "assistant" ? "AI" : "Bạn"}</span><div>{children}</div></div>;
}
