import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <main>
      <h1>Page not found</h1>
      <p>
        There is nothing at this address. <Link to="/">Go to the start page</Link>
      </p>
    </main>
  );
}
