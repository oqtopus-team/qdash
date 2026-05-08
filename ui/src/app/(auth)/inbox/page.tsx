import { redirect } from "next/navigation";

export default function LegacyInboxRedirectPage() {
  redirect("/notifications");
}
