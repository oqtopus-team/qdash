"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { FaScrewdriverWrench } from "react-icons/fa6";
import { GoWorkflow } from "react-icons/go";
import { FaBolt } from "react-icons/fa6";
import { IoMdSettings } from "react-icons/io";
import { LuThermometerSnowflake } from "react-icons/lu";
import { GiGinkgoLeaf } from "react-icons/gi";
import { TbTestPipe } from "react-icons/tb";
import { BsCpu } from "react-icons/bs";

function Sidebar() {
  const pathname = usePathname();

  const isActive = (path: string) => {
    return pathname === path;
  };

  return (
    <div className="drawer-side z-40">
      <label
        htmlFor="drawer"
        className="drawer-overlay"
        aria-label="Close menu"
      ></label>
      <aside className="bg-base-200 min-h-screen w-80">
        <ul className="menu p-4 py-0">
          <div className="p-6"></div>
          <li>
            <Link
              href="/chip"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center ${
                isActive("/chip")
                  ? "bg-neutral text-neutral-content"
                  : "text-base-content"
              }`}
            >
              <BsCpu />
              <span className="ml-2">Chip</span>
            </Link>
          </li>
          <li>
            <Link
              href="/calibration"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center ${
                isActive("/calibration")
                  ? "bg-neutral text-neutral-content"
                  : "text-base-content"
              }`}
            >
              <FaScrewdriverWrench />
              <span className="ml-2">Calibration</span>
            </Link>
          </li>
          <li>
            <Link
              href="/execution"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center ${
                isActive("/execution")
                  ? "bg-neutral text-neutral-content"
                  : "text-base-content"
              }`}
            >
              <FaBolt />
              <span className="ml-2">Execution</span>
            </Link>
          </li>
          <li>
            <Link
              href="/experiment"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center ${
                isActive("/experiment")
                  ? "bg-neutral text-neutral-content"
                  : "text-base-content"
              }`}
            >
              <TbTestPipe />
              <span className="ml-2">Experiment</span>
            </Link>
          </li>
          <li>
            <Link
              href="/fridge"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center ${
                isActive("/fridge")
                  ? "bg-neutral text-neutral-content"
                  : "text-base-content"
              }`}
            >
              <LuThermometerSnowflake />
              <span className="ml-2">Fridge</span>
            </Link>
          </li>
          <li>
            <Link
              href="/setting"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center ${
                isActive("/setting")
                  ? "bg-neutral text-neutral-content"
                  : "text-base-content"
              }`}
            >
              <IoMdSettings />
              <span className="ml-2">Settings</span>
            </Link>
          </li>
          <div className="divider"></div>
          <li>
            <a
              href="http://127.0.0.1:4200/dashboard"
              target="_blank"
              rel="noopener noreferrer"
              className="py-4 px-4 mx-10 my-2 text-base font-bold flex items-center"
            >
              <GoWorkflow />
              <span className="ml-2">Workflow</span>
            </a>
          </li>
          <li>
            <a
              href="https://qulacs-gui.github.io/qulacs-simulator/"
              target="_blank"
              rel="noopener noreferrer"
              className="py-4 px-4 mx-10 my-2 text-base font-bold flex items-center"
            >
              <GiGinkgoLeaf />
              <span className="ml-2">Qulacs Simulator</span>
            </a>
          </li>
        </ul>
      </aside>
    </div>
  );
}

export default Sidebar;
