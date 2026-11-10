import qrcode from 'qrcode-generator';

// Black on white in both themes: authenticator scanners need the contrast.
export default function Qr({ text, label }: { text: string; label: string }) {
  const qr = qrcode(0, 'M');
  qr.addData(text);
  qr.make();
  const size = qr.getModuleCount(), quiet = 4;
  let path = '';
  for (let row = 0; row < size; row++)
    for (let col = 0; col < size; col++)
      if (qr.isDark(row, col)) path += `M${col + quiet} ${row + quiet}h1v1h-1z`;
  const box = size + quiet * 2;
  return (
    <svg className="qr-code" viewBox={`0 0 ${box} ${box}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <rect width={box} height={box} fill="#fff" />
      <path d={path} fill="#000" />
    </svg>
  );
}
