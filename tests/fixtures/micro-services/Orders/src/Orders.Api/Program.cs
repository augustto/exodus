namespace Orders.Api
{
    public static class Program
    {
        public static void UseApp(IApplicationBuilder app)
        {
            app.UseRabbitMq()
                .SubscribeCommand<CreateOrder>();
        }
    }

    public class CreateOrder : ICommand { }
}
