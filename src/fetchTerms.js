import { collection, getDocs } from "firebase/firestore";
import { db } from "./firebaseConfig";

export async function fetchTerms() {
  const snapshot = await getDocs(collection(db, "terms"));
  return snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
}
