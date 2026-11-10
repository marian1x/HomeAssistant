import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Snapshot, value } from "./model";

const green = "#237a60",
  blue = "#4599be",
  amber = "#dca640";
function Box({
  position = [0, 0, 0],
  size = [1, 1, 1],
  color = "#f4f5f3",
  ...props
}: any) {
  return (
    <mesh position={position} castShadow receiveShadow {...props}>
      <boxGeometry args={size} />
      <meshStandardMaterial color={color} roughness={0.7} />
    </mesh>
  );
}
function Controls({ reset }: { reset: number }) {
  const { camera, gl } = useThree();
  const orbit = useMemo(
    () => new OrbitControls(camera, gl.domElement),
    [camera, gl],
  );
  useEffect(() => {
    orbit.target.set(0, 0.4, 0);
    orbit.enableDamping = true;
    orbit.enablePan = false;
    orbit.minDistance = 9;
    orbit.maxDistance = 28;
    orbit.minPolarAngle = 0.3;
    orbit.maxPolarAngle = 1.35;
    return () => orbit.dispose();
  }, [orbit]);
  useEffect(() => {
    camera.position.set(13, 12, 15);
    orbit.target.set(0, 0.4, 0);
    orbit.update();
  }, [reset, camera, orbit]);
  useFrame(() => orbit.update());
  return null;
}
function Sign({
  text,
  position,
  width = 1.4,
  color = "#33594c",
}: {
  text: string;
  position: [number, number, number];
  width?: number;
  color?: string;
}) {
  const texture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 512;
    canvas.height = 128;
    const c = canvas.getContext("2d")!;
    c.fillStyle = color;
    c.font = "600 45px Arial";
    c.textAlign = "center";
    c.fillText(text, 256, 77);
    return new THREE.CanvasTexture(canvas);
  }, [text, color]);
  useEffect(() => () => texture.dispose(), [texture]);
  return (
    <mesh position={position}>
      <planeGeometry args={[width, width / 4]} />
      <meshBasicMaterial map={texture} transparent depthWrite={false} />
    </mesh>
  );
}
function Panels({
  position,
  count = 6,
  cols = 2,
}: {
  position: [number, number, number];
  count?: number;
  cols?: number;
}) {
  return (
    <group position={position}>
      {Array.from({ length: count }, (_, i) => (
        <group
          key={i}
          position={[(i % cols) * 1.03, 0, Math.floor(i / cols) * 1.13]}
        >
          <Box size={[0.98, 0.055, 1.05]} color="#46565f" />
          <Box
            position={[0, 0.035, 0]}
            size={[0.91, 0.025, 1]}
            color="#2a434a"
          />
          {[0, 1, 2, 3].map((k) => (
            <Box
              key={k}
              position={[0, 0.052, -0.38 + k * 0.25]}
              size={[0.91, 0.006, 0.012]}
              color="#9dafb3"
            />
          ))}
          <Box
            position={[0, 0.052, 0]}
            size={[0.012, 0.006, 1]}
            color="#9dafb3"
          />
        </group>
      ))}
    </group>
  );
}
function Roof() {
  const geometry = useMemo(() => {
    const shape = new THREE.Shape();
    shape.moveTo(-2.45, 0);
    shape.lineTo(0, 1.2);
    shape.lineTo(2.45, 0);
    shape.closePath();
    return new THREE.ExtrudeGeometry(shape, {
      depth: 3.75,
      bevelEnabled: false,
    }).translate(0, 0, -1.875);
  }, []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh position={[-1, 2.2, -0.8]} geometry={geometry} castShadow>
      <meshStandardMaterial color="#78897d" roughness={0.9} />
    </mesh>
  );
}
function EnergyPath({
  points,
  power,
  color,
  reverse = false,
}: {
  points: THREE.Vector3[];
  power: number | null;
  color: string;
  reverse?: boolean;
}) {
  const curve = useMemo(() => new THREE.CatmullRomCurve3(points), [points]);
  const particle = useRef<THREE.Group>(null);
  const reduced = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );
  useFrame(({ clock }) => {
    if (!particle.current) return;
    const moving = !reduced && power !== null && power > 0.03;
    particle.current.visible = moving;
    if (moving) {
      let t = (clock.elapsedTime * 0.12) % 1;
      if (reverse) t = 1 - t;
      particle.current.position.copy(curve.getPointAt(t));
      const tangent = curve.getTangentAt(t).multiplyScalar(reverse ? -1 : 1);
      particle.current.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        tangent,
      );
    }
  });
  return (
    <group>
      <mesh>
        <tubeGeometry args={[curve, 32, 0.025, 6, false]} />
        <meshStandardMaterial
          color={power !== null && power > 0.03 ? color : "#c3cfca"}
        />
      </mesh>
      <group ref={particle}>
        <mesh>
          <coneGeometry args={[0.105, 0.29, 6]} />
          <meshBasicMaterial color={color} />
        </mesh>
      </group>
    </group>
  );
}
function World({
  data,
  select,
  selected,
}: {
  data: Snapshot | null;
  select: (key: string) => void;
  selected: string;
}) {
  const batteryColor = value(data, "soc") === null ? "#a5b3ad" : green;
  const pick = (key: string) => (e: any) => {
    e.stopPropagation();
    select(key);
  };
  const paths = useMemo(
    () => ({
      solar: [
        new THREE.Vector3(-0.7, 2.7, -2),
        new THREE.Vector3(1.5, 2.2, -2.2),
        new THREE.Vector3(2.5, 0.35, -0.5),
      ],
      battery: [
        new THREE.Vector3(2.55, 0.3, -0.2),
        new THREE.Vector3(3.5, 0.2, 0.4),
        new THREE.Vector3(3.6, 0.3, 1.35),
      ],
      house: [
        new THREE.Vector3(2.2, 0.2, -0.3),
        new THREE.Vector3(0.6, 0.2, 1),
        new THREE.Vector3(-0.2, 0.25, 1),
      ],
      grid: [
        new THREE.Vector3(5.8, 0.2, -2),
        new THREE.Vector3(4.4, 0.2, -1.4),
        new THREE.Vector3(2.5, 0.25, -0.5),
      ],
      tesla: [
        new THREE.Vector3(2.5, 0.2, -0.3),
        new THREE.Vector3(2, 0.2, 2.4),
        new THREE.Vector3(0.1, 0.2, 3.5),
      ],
    }),
    [],
  );
  return (
    <group>
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, -0.18, 0]}
        receiveShadow
      >
        <planeGeometry args={[200, 200]} />
        <meshStandardMaterial color="#edf1ee" roughness={1} />
      </mesh>
      <Box position={[0, -0.1, 0]} size={[14, 0.15, 10.5]} color="#e0e7e0" />
      <Box position={[-1, 0.015, 0.3]} size={[7, 0.08, 6.4]} color="#f6f4ec" />
      <group onClick={pick("house")}>
        <Box
          position={[-1, 1.1, -0.8]}
          size={[4.6, 2.1, 3.5]}
          color={selected === "house" ? "#e1f0e7" : "#fcfcf5"}
        />
        <Box
          position={[-1, 2.2, -0.8]}
          size={[4.9, 0.15, 3.75]}
          color="#b8c4b9"
        />
        <Roof />
        <Box
          position={[-1, 0.7, 1]}
          size={[0.85, 1.35, 0.07]}
          color="#7b8f81"
        />
        {[-2.4, 0.5].map((x) => (
          <group key={x}>
            <Box
              position={[x, 1.25, 0.985]}
              size={[0.95, 0.8, 0.08]}
              color="#718f99"
            />
            <Box
              position={[x, 1.25, 1.04]}
              size={[0.035, 0.8, 0.02]}
              color="#e7e9df"
            />
          </group>
        ))}
        <Sign text="CASA" position={[-1, 1.8, 1.035]} width={0.9} />
      </group>
      <group onClick={pick("solar")}>
        <group
          position={[-1, 3.44, -0.8]}
          rotation={[0, 0, -Math.atan(1.2 / 2.45)]}
        >
          <Panels position={[0.6, 0.05, -1.2]} />
        </group>
        <group position={[-4.7, 0, 2.1]}>
          {[-0.8, 1.8].map((x) => (
            <Box
              key={x}
              position={[x, 0.9, 0]}
              size={[0.09, 1.8, 0.09]}
              color="#798c7c"
            />
          ))}
          <Panels position={[-0.9, 1.85, -0.4]} count={3} cols={3} />
        </group>
      </group>
      <group position={[2.5, 0, -0.7]} onClick={pick("inverter")}>
        <Box
          position={[0, 0.9, 0]}
          size={[1, 1.65, 0.45]}
          color={selected === "inverter" ? "#d6ebe1" : "#f8faf7"}
        />
        <Box
          position={[0, 0.87, 0.245]}
          size={[0.6, 0.52, 0.035]}
          color="#263f3b"
        />
        <Sign
          text="DEYE"
          position={[0, 1.5, 0.251]}
          width={0.75}
          color="#bd6852"
        />
        <Box
          position={[0, 0.88, 0.275]}
          size={[0.15, 0.035, 0.005]}
          color={data?.connected ? green : "#87938b"}
        />
        {[-0.3, -0.15, 0, 0.15, 0.3].map((x) => (
          <Box
            key={x}
            position={[x, 0.3, 0.24]}
            size={[0.05, 0.12, 0.015]}
            color="#d3dcd4"
          />
        ))}
      </group>
      <group position={[3.65, 0, 1.9]} onClick={pick("battery")}>
        <Box
          position={[0, 0.77, 0]}
          size={[1.1, 1.45, 0.65]}
          color={selected === "battery" ? "#d1e6db" : "#e7ece7"}
        />
        <Box
          position={[0, 1.2, 0.34]}
          size={[0.6, 0.3, 0.025]}
          color="#29433a"
        />
        {[0, 1, 2, 3, 4].map((i) => (
          <Box
            key={i}
            position={[-0.22 + i * 0.11, 1.2, 0.36]}
            size={[0.075, 0.14, 0.02]}
            color={
              value(data, "soc") !== null && value(data, "soc")! > i * 20
                ? batteryColor
                : "#7e9286"
            }
          />
        ))}
        <Sign text="16 kWh" position={[0, 0.78, 0.34]} width={0.85} />
        <Box position={[0, 0.08, 0]} size={[1.25, 0.15, 0.8]} color="#667c6b" />
      </group>
      <group position={[5.6, 0, -2.3]} onClick={pick("grid")}>
        <Box position={[0, 1.45, 0]} size={[0.13, 2.9, 0.13]} color="#80938a" />
        <Box position={[0, 2.65, 0]} size={[1.7, 0.1, 0.12]} color="#81958b" />
        {[-0.65, 0, 0.65].map((x) => (
          <Box
            key={x}
            position={[x, 2.78, 0]}
            size={[0.09, 0.22, 0.09]}
            color="#c0d1c5"
          />
        ))}
        <Sign text="RETEA" position={[0, 1.65, 0.09]} width={1} />
      </group>
      <group
        position={[-0.6, 0, 3.5]}
        rotation={[0, -0.12, 0]}
        onClick={pick("tesla")}
      >
        <Box
          position={[0, 0.38, 0]}
          size={[2.55, 0.45, 1.12]}
          color={selected === "tesla" ? "#bfd9d0" : "#d9e2df"}
        />
        <Box
          position={[0.03, 0.74, 0]}
          size={[1.4, 0.45, 1.02]}
          color="#637d7c"
        />
        <Box
          position={[0.03, 0.98, 0]}
          size={[1.4, 0.045, 1.02]}
          color="#c4d1ca"
        />
        {[-0.8, 0.8].flatMap((x) =>
          [-0.56, 0.56].map((z) => (
            <mesh
              key={`${x}${z}`}
              position={[x, 0.25, z]}
              rotation={[Math.PI / 2, 0, 0]}
            >
              <cylinderGeometry args={[0.25, 0.25, 0.1, 20]} />
              <meshStandardMaterial color="#394a43" />
            </mesh>
          )),
        )}
      </group>
      <EnergyPath
        points={paths.solar}
        power={value(data, "solar")}
        color={amber}
      />
      <EnergyPath
        points={paths.house}
        power={value(data, "load")}
        color={green}
      />
      <EnergyPath
        points={paths.battery}
        power={Math.max(
          value(data, "charge") || 0,
          value(data, "discharge") || 0,
        )}
        color={blue}
        reverse={(value(data, "discharge") || 0) > 0}
      />
      <EnergyPath
        points={paths.grid}
        power={Math.max(value(data, "import") || 0, value(data, "export") || 0)}
        color={amber}
        reverse={(value(data, "export") || 0) > 0}
      />
      <EnergyPath
        points={paths.tesla}
        power={value(data, "tesla")}
        color={green}
      />
      <gridHelper
        args={[24, 24, "#d6dfd5", "#e4e9e1"]}
        position={[0, -0.16, 0]}
      />
    </group>
  );
}
export default function Scene({
  data,
  select,
  selected,
  reset,
}: {
  data: Snapshot | null;
  select: (key: string) => void;
  selected: string;
  reset: number;
}) {
  return (
    <Canvas
      shadows
      dpr={[1, 1.5]}
      camera={{ position: [13, 12, 15], fov: 37, near: 0.1, far: 150 }}
      gl={{ antialias: true, powerPreference: "low-power" }}
      onCreated={({ gl }) => {
        gl.domElement.setAttribute(
          "aria-label",
          "Model 3D schematic al sistemului energetic",
        );
        gl.domElement.dataset.ready = "true";
      }}
    >
      <color attach="background" args={["#edf1ee"]} />
      <ambientLight intensity={1.8} />
      <directionalLight
        castShadow
        position={[6, 12, 7]}
        intensity={2.5}
        shadow-mapSize={[1024, 1024]}
        shadow-camera-left={-12}
        shadow-camera-right={12}
        shadow-camera-top={10}
        shadow-camera-bottom={-10}
        shadow-bias={-0.001}
      />
      <World data={data} select={select} selected={selected} />
      <Controls reset={reset} />
    </Canvas>
  );
}
