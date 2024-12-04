import { NavLink } from "react-router-dom";

function Home() {
  return (
    <div className="w-full px-4" style={{ width: "calc(100vw - 20rem)" }}>
      <div
        className="hero min-h-screen"
        style={{ backgroundImage: 'url("src/assets/fridge.jpeg")' }}
      >
        <div className="hero-overlay bg-opacity-60"></div>
        <div className="hero-content text-center text-neutral-content">
          <div className="max-w-md">
            <h1 className="mb-5 text-5xl font-bold">
              Quantum Monitoring Service
            </h1>
            <p className="mb-5">Quantum Process Unit Monitoring Service.</p>
            <NavLink to="/calibration" className="text-primary">
              {" "}
              <button className="btn btn-primary">Get Started</button>
            </NavLink>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Home;
