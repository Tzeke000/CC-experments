using Godot;

namespace MakingThingsCsharpFixture;

public partial class Hello : Node2D
{
	public override void _Ready()
	{
		GD.Print("Making Things C# fixture ready");
	}
}
