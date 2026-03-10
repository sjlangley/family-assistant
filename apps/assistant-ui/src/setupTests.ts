import { expect } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";

expect.extend(matchers);

// Mock scrollIntoView which is not implemented in jsdom
Element.prototype.scrollIntoView = () => {};
