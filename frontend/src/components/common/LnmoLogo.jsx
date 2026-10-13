const API = process.env.REACT_APP_BACKEND_URL;

export const lnmoAsset = (name) => `${API}/api/public/platform-brand/${name}`;

export const LnmoMark = ({ className = "h-7", testid = "lnmo-mark" }) => (
  <img src={lnmoAsset("lnmo-mark@2x.png")} alt="LNMO" className={`${className} w-auto object-contain shrink-0`} data-testid={testid} />
);

export const LnmoLogo = ({ className = "h-16", testid = "lnmo-logo" }) => (
  <img src={lnmoAsset("lnmo-logo@2x.png")} srcSet={`${lnmoAsset("lnmo-logo@2x.png")} 2x, ${lnmoAsset("lnmo-logo@3x.png")} 3x`} alt="LNMO" className={`${className} w-auto object-contain`} data-testid={testid} />
);

export const PoweredBy = ({ className = "", testid }) => (
  <p className={`flex items-center gap-1.5 ${className}`} data-testid={testid}>
    Powered by <img src={lnmoAsset("lnmo-mark.png")} alt="" className="h-3.5 w-auto" /> <span className="font-semibold">LNMO</span>
  </p>
);
