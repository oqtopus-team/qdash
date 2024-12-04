import { NavLink } from "react-router-dom";

import { BiAtom } from "react-icons/bi";
import { FaScrewdriverWrench } from "react-icons/fa6";

import { GoWorkflow } from "react-icons/go";

import { FaBolt } from "react-icons/fa6";
import { IoMdSettings } from "react-icons/io";
import { LuThermometerSnowflake } from "react-icons/lu";
import { GiGinkgoLeaf } from "react-icons/gi";

import { TbTestPipe } from "react-icons/tb";
import { BsCpu } from "react-icons/bs";

function Sidebar() {
  const envValue = import.meta.env.VITE_ENV;
  console.log("envValue", envValue);

  return (
    <div className="drawer-side z-40">
      <label
        htmlFor="drawer"
        className="drawer-overlay"
        aria-label="Close menu"
      ></label>
      <aside className="bg-base-200 min-h-screen w-80">
        <ul className="menu p-4 py-0">
          {/* <img src={logo} className="p-4" alt="Logo" /> */}
          <div className="p-6"></div>
          <li>
            <NavLink
              to="/qpu"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center`}
            >
              <BsCpu />
              <span className="ml-2">QPU</span>
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/calibration"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center`}
            >
              <FaScrewdriverWrench />
              <span className="ml-2">Calibration</span>
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/execution"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center`}
            >
              <FaBolt />
              <span className="ml-2">Execution</span>
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/experiment"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center`}
            >
              <TbTestPipe />
              <span className="ml-2">Expriment</span>
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/fridge"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center`}
            >
              <LuThermometerSnowflake />
              <span className="ml-2">Fridge</span>
            </NavLink>
          </li>

          <li>
            <NavLink
              to="/setting"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center`}
            >
              <IoMdSettings />
              <span className="ml-2">Settings</span>
            </NavLink>
          </li>
          <div className="divider"></div>
          <li>
            <NavLink
              to="http://127.0.0.1:4200/dashboard"
              target="_blank"
              rel="noopener noreferrer"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center`}
            >
              <GoWorkflow />
              <span className="ml-2">Workflow</span>
            </NavLink>
          </li>
          <li>
            <NavLink
              to="https://qulacs-gui.github.io/qulacs-simulator/"
              target="_blank"
              rel="noopener noreferrer"
              className={`py-4 px-4 mx-10 my-2 text-base font-bold flex items-center`}
            >
              <GiGinkgoLeaf />
              <span className="ml-2">Qulacs Simulator</span>
            </NavLink>
          </li>
        </ul>
      </aside>
    </div>
  );
}

export default Sidebar;
