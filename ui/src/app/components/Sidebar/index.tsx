"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { BsListTask, BsMenuButton, BsGrid } from "react-icons/bs";
import { BsCpu } from "react-icons/bs";
import { FaBolt } from "react-icons/fa6";
import { FiChevronLeft, FiChevronRight } from "react-icons/fi";
import { GoWorkflow } from "react-icons/go";
import { IoMdSettings } from "react-icons/io";
import { IoAnalytics } from "react-icons/io5";
import { FaCode } from "react-icons/fa";

import { useSidebar } from "@/app/contexts/SidebarContext";

function Sidebar() {
  const pathname = usePathname();
  const { isOpen, toggleSidebar } = useSidebar();

  const isActive = (path: string) => {
    return pathname === path;
  };

  return (
    <aside
      className={`bg-base-200 min-h-screen transition-all duration-300 ${
        isOpen ? "w-80" : "w-20"
      }`}
    >
      <div className="flex justify-end p-2">
        <button
          onClick={toggleSidebar}
          className="btn btn-ghost btn-sm btn-square"
          aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          {isOpen ? <FiChevronLeft size={20} /> : <FiChevronRight size={20} />}
        </button>
      </div>
      <ul className="menu p-4 py-0">
        {isOpen && (
          <div className="flex justify-center items-center p-4">
            <Link href="/" className="flex items-center">
              <Image
                src="/oqtopus_logo.png"
                alt="Oqtopus Logo"
                width={100}
                height={25}
                className="object-contain"
                priority
              />
            </Link>
          </div>
        )}
        <li>
          <Link
            href="/metrics"
            className={`py-4 ${isOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"} my-2 text-base font-bold flex items-center ${
              isActive("/metrics")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Metrics"
          >
            <BsGrid />
            {isOpen && <span className="ml-2">Metrics</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/chip"
            className={`py-4 ${isOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"} my-2 text-base font-bold flex items-center ${
              isActive("/chip")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Chip"
          >
            <BsCpu />
            {isOpen && <span className="ml-2">Chip</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/flow"
            className={`py-4 ${isOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"} my-2 text-base font-bold flex items-center ${
              pathname.startsWith("/flow")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Flow Editor"
          >
            <FaCode />
            {isOpen && <span className="ml-2">Flow Editor</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/menu/editor"
            className={`py-4 ${isOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"} my-2 text-base font-bold flex items-center ${
              isActive("/menu/editor")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Menu Editor"
          >
            <BsMenuButton />
            {isOpen && <span className="ml-2">Menu Editor</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/execution"
            className={`py-4 ${isOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"} my-2 text-base font-bold flex items-center ${
              isActive("/execution")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Execution"
          >
            <FaBolt />
            {isOpen && <span className="ml-2">Execution</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/analysis"
            className={`py-4 ${isOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"} my-2 text-base font-bold flex items-center ${
              isActive("/analysis")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Analysis"
          >
            <IoAnalytics />
            {isOpen && <span className="ml-2">Analysis</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/tasks"
            className={`py-4 ${isOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"} my-2 text-base font-bold flex items-center ${
              isActive("/tasks")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Tasks"
          >
            <BsListTask />
            {isOpen && <span className="ml-2">Tasks</span>}
          </Link>
        </li>
        {/* TODO: Implement Fridge page
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
          */}
        <li>
          <Link
            href="/setting"
            className={`py-4 ${isOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"} my-2 text-base font-bold flex items-center ${
              isActive("/setting")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Settings"
          >
            <IoMdSettings />
            {isOpen && <span className="ml-2">Settings</span>}
          </Link>
        </li>
        <div className="divider"></div>
        <li>
          <a
            href="http://127.0.0.1:4200/dashboard"
            target="_blank"
            rel="noopener noreferrer"
            className={`py-4 ${isOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"} my-2 text-base font-bold flex items-center`}
            title="Workflow"
          >
            <GoWorkflow />
            {isOpen && <span className="ml-2">Workflow</span>}
          </a>
        </li>
      </ul>
    </aside>
  );
}

export default Sidebar;
