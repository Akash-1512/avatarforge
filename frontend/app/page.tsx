import { redirect } from "next/navigation";

export default function Home() {
  // the studio gates itself on auth; send users there.
  redirect("/studio");
}
