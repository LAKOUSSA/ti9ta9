export default async ()=> {  
    console.log("xo controller");

    const root = document.getElementById("xo_game");

    const home = document.createElement("home-game");
  
    root.appendChild(home);
    
    return function ()
    {
        console.log("xo cleanup");
    }
}

