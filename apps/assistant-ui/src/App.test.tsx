import { render, screen } from "@testing-library/react";
import App from "./App";

it("renders hello world", () => {
  render(<App />);
  expect(screen.getByText(/hello world/i)).toBeInTheDocument();
});
