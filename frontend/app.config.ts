export default defineAppConfig({
  ui: {
    colors: {
      primary: 'white',
      neutral: 'zinc',
    },
    button: {
      compoundVariants: [
        {
          color: 'neutral',
          variant: 'ghost',
          class: '!text-black hover:!bg-black hover:!text-white active:!bg-black active:!text-white',
        },
        {
          color: 'neutral',
          variant: 'outline',
          class: '!text-black hover:!bg-black hover:!text-white active:!bg-black active:!text-white',
        },
      ],
    },
  },
})
