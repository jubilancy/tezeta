import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";

// Web config is public by design; access is controlled by Firestore rules.
const firebaseConfig = {
  apiKey: "AIzaSyB1bF0hSP2HbOkhnfijP_6-9iqdD_TqDoE",
  authDomain: "tezeta.firebaseapp.com",
  projectId: "tezeta",
  storageBucket: "tezeta.firebasestorage.app",
  messagingSenderId: "461252102970",
  appId: "1:461252102970:web:5f193ac6405eecb388de03",
  measurementId: "G-V5CNXP2MVC",
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
